"""Per-connection WebSocket streaming machinery (task prompt §5).

Threading model: ``EventBus.publish`` runs handlers synchronously on the
publisher's thread (possibly a worker thread or FastAPI's threadpool), while
the asyncio.Queue and seq counter belong to the connection's event loop. The
handler therefore never touches the queue directly — it hands the payload to
the loop with ``loop.call_soon_threadsafe``:

  * the publisher is never blocked (call_soon_threadsafe only appends to the
    loop's callback queue),
  * when the connection queue is full the OLDEST message is dropped and a
    dropped counter increments — the client is never disconnected for being
    slow and the publisher never waits (§5),
  * a callback that fires after the loop is closed raises inside the handler,
    which the frozen EventBus contract swallows without affecting the
    publisher or other handlers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from services.api.ws_contract import (
    KIND_DELTA,
    KIND_SNAPSHOT,
    PREBUFFER_LIMIT,
    QUEUE_MAXSIZE,
    make_message,
)


@dataclass
class WsConnectionStats:
    """Observable per-connection counters (kept after close for tests)."""

    topic: str
    sent: int = 0
    dropped: int = 0
    snapshots: int = 0
    deltas: int = 0
    peak_queued: int = 0


class WsConnection:
    """Bounded queue + seq allocator + snapshot pre-buffer for one client."""

    def __init__(self, *, topic: str) -> None:
        self.topic = topic
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self.stats = WsConnectionStats(topic=topic)
        self._seq = 0
        self._frozen = True  # snapshots have not been enqueued yet
        self._prebuffer: list[dict[str, Any]] = []
        self._closed = False

    # -- seq -------------------------------------------------------------------
    def _next_seq(self) -> int:
        seq = self._seq
        self._seq += 1
        return seq

    # -- enqueue (always called on the loop thread) ----------------------------
    def enqueue_snapshot(self, channel: str, data: Any) -> None:
        """Snapshot messages bypass the pre-buffer: they are enqueued first."""
        self._put(make_message(KIND_SNAPSHOT, channel, self._next_seq(), data))
        self.stats.snapshots += 1

    def enqueue_delta(self, payload: Any) -> None:
        """Delta entry point (invoked via call_soon_threadsafe from any thread)."""
        if self._closed:
            return
        if not isinstance(payload, dict):  # contract-defensive: ignore malformed
            return
        channel = str(payload.get("channel", ""))
        data = payload.get("data", payload)
        message = make_message(KIND_DELTA, channel or "radio", self._next_seq(), data)
        if self._frozen:
            # Deltas published before the snapshots are flushed: hold them so
            # ordering stays snapshot -> delta with no loss in the window.
            if len(self._prebuffer) >= PREBUFFER_LIMIT:
                self._prebuffer.pop(0)
                self.stats.dropped += 1
            self._prebuffer.append(message)
            return
        self._put(message)

    def _put(self, message: dict[str, Any]) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()  # drop OLDEST
                self.stats.dropped += 1
            except asyncio.QueueEmpty:  # pragma: no cover - defensive
                pass
        self.queue.put_nowait(message)
        self.stats.peak_queued = max(self.stats.peak_queued, self.queue.qsize())

    def unfreeze(self) -> None:
        """Flush pre-buffered deltas behind the snapshots (order preserved)."""
        self._frozen = False
        pending = self._prebuffer
        self._prebuffer = []
        for message in pending:
            self._put(message)

    def close(self) -> None:
        self._closed = True
        self._prebuffer.clear()

    @property
    def closed(self) -> bool:
        return self._closed

    def mark_sent(self) -> None:
        self.stats.sent += 1

    def make_handler(self) -> Callable[[dict[str, Any]], None]:
        """The EventBus subscription: safe from any thread, never blocks."""
        loop = asyncio.get_running_loop()

        def handler(payload: dict[str, Any]) -> None:
            if self._closed:
                return
            loop.call_soon_threadsafe(self.enqueue_delta, payload)

        return handler


async def _pump(ws: WebSocket, connection: WsConnection) -> None:
    """queue -> wire. Ends when the client disappears mid-send or on cancel."""
    while True:
        message = await connection.queue.get()
        await ws.send_json(message)
        connection.mark_sent()


async def _watch(ws: WebSocket) -> None:
    """Ends the stream when the client disconnects (client messages ignored:
    Wave-1 clients do not send; anything received is discarded)."""
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            return


async def stream_events(
    ws: WebSocket,
    *,
    bus: Any,
    topic: str,
    snapshot: Callable[[], dict[str, dict[str, Any]]],
    app_state: Any,
) -> None:
    """Snapshot-then-delta streaming with bounded-queue backpressure.

    Subscribe BEFORE building the snapshot so no delta published during
    snapshot construction is lost: such deltas land in the connection's
    pre-buffer and are flushed after the snapshot messages (ordering
    guarantee: every delta follows every snapshot).
    """
    connection = WsConnection(topic=topic)
    handler = connection.make_handler()
    bus.subscribe(topic, handler)
    app_state.ws_connections.add(connection)
    pump: asyncio.Task[None] | None = None
    watch: asyncio.Task[None] | None = None
    try:
        for channel, data in snapshot().items():
            connection.enqueue_snapshot(channel, data)
        connection.unfreeze()
        pump = asyncio.create_task(_pump(ws, connection))
        watch = asyncio.create_task(_watch(ws))
        done, _pending = await asyncio.wait({pump, watch}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            # A client that vanishes mid-send (RuntimeError from the transport)
            # or the documented WebSocketDisconnect both simply end the stream.
            if exc is not None and not isinstance(exc, (WebSocketDisconnect, RuntimeError)):
                raise exc
    finally:
        bus.unsubscribe(topic, handler)
        connection.close()
        app_state.ws_connections.discard(connection)
        app_state.ws_history.append(connection.stats)
        tasks = [task for task in (pump, watch) if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@dataclass
class WsStreamState:
    """Attached to app.state by create_app (inspection seam for tests)."""

    ws_connections: set[WsConnection] = field(default_factory=set)
    ws_history: list[WsConnectionStats] = field(default_factory=list)
