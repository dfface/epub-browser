import asyncio
import re
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ProgressFailure:
    filename: str
    message: str


@dataclass(frozen=True)
class LibraryProgressSnapshot:
    generation: int = 0
    revision: int = 0
    trigger: str = "startup"
    phase: str = "idle"
    total: Optional[int] = None
    completed: int = 0
    converted: int = 0
    reused: int = 0
    failed: int = 0
    removed: int = 0
    in_flight: int = 0
    active_books: int = 0
    catalog_revision: int = 0
    latest_book: Optional[str] = None
    failures: tuple[ProgressFailure, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def safe_progress_message(error) -> str:
    message = str(error).splitlines()[0].strip() or "Unable to process EPUB"
    message = re.sub(
        r"(?:[A-Za-z]:[\\/]|/|\\\\)[^\s:'\"]+(?:[\\/][^\s:'\"]*)*",
        "source file",
        message,
    )
    return message[:240]


class ProgressSubscription:
    def __init__(self, broker, loop, initial):
        self._broker = broker
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=1)
        self.closed = False
        self._offer(initial)

    def _offer(self, snapshot):
        if self.closed:
            return
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(snapshot)

    def offer_threadsafe(self, snapshot):
        try:
            self.loop.call_soon_threadsafe(self._offer, snapshot)
        except RuntimeError:
            # A disconnected/closed event loop must not affect reconciliation.
            return

    async def next(self):
        return await self.queue.get()

    def close(self):
        if not self.closed:
            self.closed = True
            self._broker.unsubscribe(self)


class LibraryProgressBroker:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers = set()
        self._snapshot = LibraryProgressSnapshot()

    def snapshot(self) -> LibraryProgressSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def subscribe(self, loop) -> ProgressSubscription:
        with self._lock:
            subscription = ProgressSubscription(self, loop, self._snapshot)
            self._subscribers.add(subscription)
            return subscription

    def unsubscribe(self, subscription) -> None:
        with self._lock:
            self._subscribers.discard(subscription)

    def _update(self, **changes) -> LibraryProgressSnapshot:
        with self._lock:
            changes = {
                field: value(self._snapshot) if callable(value) else value
                for field, value in changes.items()
            }
            self._snapshot = replace(
                self._snapshot,
                revision=self._snapshot.revision + 1,
                **changes,
            )
            snapshot = self._snapshot
            subscribers = tuple(self._subscribers)
        for subscription in subscribers:
            subscription.offer_threadsafe(snapshot)
        return snapshot

    def start_generation(self, trigger: str) -> LibraryProgressSnapshot:
        if trigger not in {"startup", "watch"}:
            raise ValueError("trigger must be 'startup' or 'watch'")
        return self._update(
            generation=lambda snapshot: snapshot.generation + 1,
            trigger=trigger,
            phase="discovering",
            total=None,
            completed=0,
            converted=0,
            reused=0,
            failed=0,
            removed=0,
            in_flight=0,
            latest_book=None,
            failures=(),
        )

    def mark_discovered(self, total: int, removed: int) -> LibraryProgressSnapshot:
        return self._update(
            phase="processing",
            total=total,
            removed=removed,
        )

    def record_reused(self, source) -> LibraryProgressSnapshot:
        return self._update(
            phase="processing",
            completed=lambda snapshot: snapshot.completed + 1,
            reused=lambda snapshot: snapshot.reused + 1,
            latest_book=Path(source).name,
        )

    def conversion_started(self) -> LibraryProgressSnapshot:
        return self._update(
            phase="processing",
            in_flight=lambda snapshot: snapshot.in_flight + 1,
        )

    def record_converted(self, source) -> LibraryProgressSnapshot:
        return self._update(
            phase="processing",
            completed=lambda snapshot: snapshot.completed + 1,
            converted=lambda snapshot: snapshot.converted + 1,
            in_flight=lambda snapshot: max(0, snapshot.in_flight - 1),
            latest_book=Path(source).name,
        )

    def record_failure(self, source, error, in_flight: bool = False) -> LibraryProgressSnapshot:
        failure = ProgressFailure(Path(source).name, safe_progress_message(error))
        return self._update(
            phase="processing",
            completed=lambda snapshot: snapshot.completed + 1,
            failed=lambda snapshot: snapshot.failed + 1,
            in_flight=(
                (lambda snapshot: max(0, snapshot.in_flight - 1))
                if in_flight
                else (lambda snapshot: snapshot.in_flight)
            ),
            failures=lambda snapshot: snapshot.failures + (failure,),
        )

    def catalog_published(self, active_books: int) -> LibraryProgressSnapshot:
        return self._update(
            active_books=active_books,
            catalog_revision=lambda snapshot: snapshot.catalog_revision + 1,
        )

    def finish(self, active_books: int) -> LibraryProgressSnapshot:
        return self._update(
            phase=lambda snapshot: "degraded" if snapshot.failed else "complete",
            active_books=active_books,
        )
