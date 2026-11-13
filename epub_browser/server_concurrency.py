"""Thread pools and process-local caches that keep blocking work off the ASGI loop.

The Server historically ran SQLite, file IO and template rendering directly inside
``async def`` handlers.  Those calls hold the single event-loop thread and make
unrelated requests (including ``/api/health``) queue behind page rendering.  This
module centralises the offloading policy instead of scattering ad-hoc
``to_thread`` calls through ``server.py``.

Pools are module-level singletons so repeated ``create_app`` calls in tests do not
leak threads.  They are sized from the expected Server concurrency profile:

* ``db`` (4): SQLite in WAL mode allows concurrent readers and a single writer.
  Four threads cover the handful of DB round-trips a page request needs without
  opening dozens of connections (the default AnyIO limiter allows 40).
* ``render`` (2): page rendering and content-security-policy scanning are CPU
  bound; extra threads mostly add GIL context switching.  Two workers let one
  slow render proceed without stalling every other page.
* ``io`` (2): uploads and dictionary package installation are long but rare.
  A separate pool stops them from occupying the DB or render pools.

Short, one-off reads can keep using ``anyio.to_thread.run_sync`` (the default
limiter); they are not worth another pool.
"""

import asyncio
import atexit
import functools
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

LOGGER = logging.getLogger(__name__)

DB_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='epub-browser-db')
RENDER_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='epub-browser-render')
IO_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='epub-browser-io')


def _run(pool: ThreadPoolExecutor, fn: Callable[..., Any], *args, **kwargs) -> Any:
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(pool, functools.partial(fn, *args, **kwargs))


async def run_db(fn: Callable[..., Any], *args, **kwargs) -> Any:
    """Run a StateStore call and let in-flight transactions finish on cancellation."""
    operation = _run(DB_POOL, fn, *args, **kwargs)
    try:
        return await asyncio.shield(operation)
    except asyncio.CancelledError:
        try:
            await operation
        except Exception:
            LOGGER.exception("Database operation failed while its caller was cancelled")
        raise


async def run_render(fn: Callable[..., Any], *args, **kwargs) -> Any:
    """Run synchronous template rendering or CSP scanning in the render pool."""
    return await _run(RENDER_POOL, fn, *args, **kwargs)


async def run_io(fn: Callable[..., Any], *args, **kwargs) -> Any:
    """Run long file IO (uploads, package installation) in the IO pool."""
    return await _run(IO_POOL, fn, *args, **kwargs)


@atexit.register
def shutdown_pools() -> None:
    for pool in (DB_POOL, RENDER_POOL, IO_POOL):
        pool.shutdown(wait=False)


class SetupStateMonitor:
    """Cache ``has_administrator`` so the auth middleware never touches SQLite.

    Invalidation rules:

    * ``mark_complete`` is called by a successful ``/setup`` before the response
      is sent, so the creating process has no "still uninitialised" window.
    * While the cached value is ``False`` the middleware re-probes at most once
      per ``probe_interval`` (default 100 ms).  Another process that finishes
      setup therefore converges almost immediately, and a test app whose lifespan
      never ran still observes a freshly created administrator on the next request.
    * ``request_revalidate`` marks the value dirty after admin user deletion or
      role changes; the next request or background refresh re-probes.  The stale
      value is never reported as "no administrator", so a logged-in user cannot
      be pushed back into setup mode.
    * A background task revalidates periodically (5 s) so multi-worker deployments
      converge even without traffic.  A single Server per output directory is
      already enforced by ``runtime.py``'s directory lock.
    """

    def __init__(
        self,
        probe: Callable[[], bool],
        *,
        initial_ready: Optional[bool] = None,
        probe_interval: float = 0.1,
        revalidate_interval: float = 5.0,
        pre_setup_interval: float = 1.0,
    ) -> None:
        self._probe = probe
        self._probe_interval = probe_interval
        self._revalidate_interval = revalidate_interval
        self._pre_setup_interval = pre_setup_interval
        self._ready = bool(initial_ready) if initial_ready is not None else False
        self._dirty = initial_ready is None
        self._probing = False
        self._last_probe = 0.0
        self._lock = threading.Lock()
        self._wake: Optional[asyncio.Event] = None
        self._background_loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._ready

    def mark_complete(self) -> None:
        with self._lock:
            self._ready = True
            self._dirty = False
            self._probing = False
            self._last_probe = time.monotonic()

    def request_revalidate(self) -> None:
        with self._lock:
            self._dirty = True
        self._set_wake()

    def _set_wake(self) -> None:
        loop = self._background_loop
        wake = self._wake
        if loop is None or wake is None:
            return
        try:
            loop.call_soon_threadsafe(wake.set)
        except RuntimeError:
            # The background loop already closed; the next process/request will
            # probe through ``setup_required`` instead.
            return

    async def setup_required(self) -> bool:
        with self._lock:
            dirty = self._dirty
        if dirty:
            await self._refresh()
            return not self.ready
        if self.ready:
            return False
        now = time.monotonic()
        with self._lock:
            if self._probing or now - self._last_probe < self._probe_interval:
                return True
            self._probing = True
        try:
            ready = await run_db(self._probe)
            if ready:
                with self._lock:
                    self._ready = True
            return not ready
        finally:
            with self._lock:
                self._probing = False
                self._last_probe = time.monotonic()

    async def _refresh(self) -> None:
        with self._lock:
            if self._probing:
                return
            self._dirty = False
            self._probing = True
        try:
            ready = await run_db(self._probe)
            with self._lock:
                self._ready = ready
        finally:
            with self._lock:
                self._probing = False
                self._last_probe = time.monotonic()

    async def run(self) -> None:
        """Background revalidation; started by the ASGI lifespan."""
        loop = asyncio.get_running_loop()
        self._background_loop = loop
        self._wake = asyncio.Event()
        try:
            while True:
                interval = (
                    self._revalidate_interval
                    if self.ready
                    else self._pre_setup_interval
                )
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=interval)
                    self._wake.clear()
                except asyncio.TimeoutError:
                    pass
                try:
                    await self._refresh()
                except Exception:
                    LOGGER.exception('background setup-state revalidation failed')
        finally:
            self._background_loop = None
            self._wake = None


class StatKeyedCache:
    """Cache a small derived file keyed by ``(mtime_ns, size)``.

    Asset republication rewrites ``asset-manifest.json``; the stat key changes and
    the next request rebuilds the cache.  Filesystem metadata is shared by every
    process on the same output directory, so no explicit cross-process broadcast
    is needed.  A failed reload raises the same exception the uncached loader
    raised and leaves the previous value in place.
    """

    def __init__(self, path: Path, loader: Callable[[], Any]) -> None:
        self._path = path
        self._loader = loader
        self._lock = threading.Lock()
        self._key: Optional[tuple[int, int]] = None
        self._value: Any = None

    def get(self) -> Any:
        stat_result = os.stat(self._path)
        key = (stat_result.st_mtime_ns, stat_result.st_size)
        with self._lock:
            if self._key == key and self._value is not None:
                return self._value
        value = self._loader()
        with self._lock:
            self._key = key
            self._value = value
        return value

    def invalidate(self) -> None:
        with self._lock:
            self._key = None
            self._value = None
