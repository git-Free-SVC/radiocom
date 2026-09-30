"""Reference EventBus: synchronous in-process pub/sub (MVP, §19)."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from libraries.plugin_sdk.event_bus import Handler

log = logging.getLogger(__name__)


class InProcessEventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for handler in tuple(self._subs.get(topic, ())):  # snapshot: safe vs re-entrancy
            try:
                handler(payload)
            except Exception:  # isolate handler failures
                log.exception("handler failed on topic %r", topic)

    def subscribe(self, topic: str, handler: Handler) -> None:
        if handler not in self._subs[topic]:
            self._subs[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        try:
            self._subs[topic].remove(handler)
        except ValueError:
            pass
