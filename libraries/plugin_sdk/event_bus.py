"""EventBus interface. Frozen after Wave 0 — see docs/adr/ADR-000.
MVP implementation: in-process pub/sub. Later: NATS JetStream adapter (§19)."""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

Handler = Callable[[dict[str, Any]], None]


@runtime_checkable
class EventBus(Protocol):
    def publish(self, topic: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, topic: str, handler: Handler) -> None: ...

    def unsubscribe(self, topic: str, handler: Handler) -> None: ...
