"""Contract for any EventBus (behavioural rules: see plugin_sdk/event_bus.py).

    pytest tests/contract/test_event_bus_contract.py --eventbus-impl=pkg.mod:Class
"""

from __future__ import annotations

from libraries.plugin_sdk.event_bus import EventBus


def test_conforms_to_protocol(bus):
    assert isinstance(bus, EventBus)


def test_delivers_payload_to_subscriber(bus):
    got = []
    bus.subscribe("t", got.append)
    bus.publish("t", {"a": 1})
    assert got == [{"a": 1}]


def test_topics_are_isolated(bus):
    got = []
    bus.subscribe("t1", got.append)
    bus.publish("t2", {"x": 1})
    assert got == []


def test_delivery_in_subscription_order(bus):
    order = []
    bus.subscribe("t", lambda p: order.append(1))
    bus.subscribe("t", lambda p: order.append(2))
    bus.publish("t", {})
    assert order == [1, 2]


def test_unsubscribe_stops_delivery(bus):
    got = []
    bus.subscribe("t", got.append)
    bus.unsubscribe("t", got.append)
    bus.publish("t", {})
    assert got == []


def test_unsubscribe_unknown_is_noop(bus):
    bus.unsubscribe("never", lambda p: None)


def test_publish_without_subscribers_is_ok(bus):
    bus.publish("nobody", {})


def test_duplicate_subscribe_is_idempotent(bus):
    got = []
    h = got.append
    bus.subscribe("t", h)
    bus.subscribe("t", h)
    bus.publish("t", {})
    assert len(got) == 1


def test_failing_handler_does_not_break_publisher_or_others(bus):
    got = []

    def boom(p):
        raise RuntimeError("handler bug")

    bus.subscribe("t", boom)
    bus.subscribe("t", got.append)
    bus.publish("t", {"ok": True})  # must not raise
    assert got == [{"ok": True}]


def test_unsubscribe_during_publish_is_safe(bus):
    calls = []

    def once(p):
        calls.append("once")
        bus.unsubscribe("t", once)

    bus.subscribe("t", once)
    bus.subscribe("t", lambda p: calls.append("other"))
    bus.publish("t", {})
    bus.publish("t", {})
    assert calls == ["once", "other", "other"]
