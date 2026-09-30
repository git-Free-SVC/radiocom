"""EventBus interface. Frozen after Wave 0 — see docs/adr/ADR-000.
MVP implementation: in-process pub/sub. Later: NATS JetStream adapter (§19).

Behavioural contract (enforced by tests/contract/test_event_bus_contract.py):
  * Handlers run synchronously, in subscription order, on the publisher's thread.
  * A handler that raises MUST NOT propagate to the publisher nor stop
    delivery to the remaining handlers.
  * Subscribing the same (topic, handler) twice is idempotent.
  * unsubscribe() of an unknown (topic, handler) is a silent no-op.
  * subscribe/unsubscribe during publish() affect only later publishes.
  * Topics are exact-match strings (no wildcards in v1).
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

Handler = Callable[[dict[str, Any]], None]


@runtime_checkable
class EventBus(Protocol):
    def publish(self, topic: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, topic: str, handler: Handler) -> None: ...

    def unsubscribe(self, topic: str, handler: Handler) -> None: ...
