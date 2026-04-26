"""Tests for event bus and event-driven task execution."""

import pytest
from datetime import datetime
from core.events import EventBus
from core.tasks.task_manager import TaskManager
from core.tasks.task import Task


class TestEventBus:
    """Test EventBus functionality."""

    def test_subscribe_and_publish(self):
        """Test basic subscribe and publish."""
        bus = EventBus()
        events_received = []

        def handler(payload: str):
            events_received.append(payload)

        bus.subscribe("test_event", handler)
        bus.publish("test_event", "hello")

        assert len(events_received) == 1
        assert events_received[0] == "hello"

    def test_multiple_subscribers(self):
        """Test multiple handlers for same event."""
        bus = EventBus()
        handler1_calls = []
        handler2_calls = []

        def handler1(p):
            handler1_calls.append(p)

        def handler2(p):
            handler2_calls.append(p)

        bus.subscribe("event", handler1)
        bus.subscribe("event", handler2)
        bus.publish("event", "data")

        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    def test_no_duplicate_subscribers(self):
        """Test that same handler not registered twice."""
        bus = EventBus()
        calls = []

        def handler(p):
            calls.append(p)

        bus.subscribe("e", handler)
        bus.subscribe("e", handler)
        bus.publish("e", "msg")

        assert len(calls) == 1

    def test_unsubscribe(self):
        """Test unsubscribe removes handler."""
        bus = EventBus()
        calls = []

        def handler(p):
            calls.append(p)

        bus.subscribe("e", handler)
        assert bus.unsubscribe("e", handler)
        bus.publish("e", "msg")

        assert len(calls) == 0

    def test_unsubscribe_nonexistent(self):
        """Test unsubscribe returns False if not found."""
        bus = EventBus()

        def handler(p):
            pass

        assert not bus.unsubscribe("e", handler)

    def test_listeners_for(self):
        """Test count of listeners."""
        bus = EventBus()

        def h1(p):
            pass

        def h2(p):
            pass

        bus.subscribe("e", h1)
        bus.subscribe("e", h2)

        assert bus.listeners_for("e") == 2
        assert bus.listeners_for("other") == 0

    def test_all_events(self):
        """Test all_events returns event counts."""
        bus = EventBus()

        def h(p):
            pass

        bus.subscribe("e1", h)
        bus.subscribe("e1", h)
        bus.subscribe("e2", h)

        events = bus.all_events()
        assert events["e1"] == 2
        assert events["e2"] == 1

    def test_recent_events_history(self):
        """Test event history tracking."""
        bus = EventBus()
        bus.publish("e1", "p1")
        bus.publish("e2", "p2")
        bus.publish("e1", "p3")

        history = bus.recent_events()
        assert len(history) == 3
        assert history[0]["event"] == "e1"
        assert history[2]["event"] == "e1"

    def test_empty_payload_defaults(self):
        """Test that None payload defaults to empty string."""
        bus = EventBus()
        calls = []

        def handler(p):
            calls.append(p)

        bus.subscribe("e", handler)
        bus.publish("e", None)

        assert calls[0] == ""

    def test_max_history_limit(self):
        """Test history is limited to max_history."""
        bus = EventBus()
        for i in range(150):
            bus.publish("e", f"msg{i}")

        history = bus.recent_events(200)
        assert len(history) == 100


class TestEventDrivenTasks:
    """Test event-driven task scheduling."""

    def test_create_event_driven_task(self):
        """Test creating a task with event trigger."""
        tm = TaskManager()
        trigger = {"type": "event", "event_name": "user_login"}

        task = tm.create_task(
            goal="send welcome email",
            trigger=trigger,
            mode="background"
        )

        assert task.is_event_driven()
        assert task.trigger["event_name"] == "user_login"

    def test_list_event_listener_map(self):
        """Test event listener mapping."""
        tm = TaskManager()

        tm.create_task(
            "task1",
            trigger={"type": "event", "event_name": "event_a"},
            mode="background"
        )
        tm.create_task(
            "task2",
            trigger={"type": "event", "event_name": "event_a"},
            mode="background"
        )
        tm.create_task(
            "task3",
            trigger={"type": "event", "event_name": "event_b"},
            mode="background"
        )

        mapping = tm.list_event_listener_map()
        assert len(mapping["event_a"]) == 2
        assert len(mapping["event_b"]) == 1

    def test_claim_event_tasks(self):
        """Test claiming tasks triggered by event."""
        tm = TaskManager()
        now = datetime.now()

        t1 = tm.create_task(
            "task1",
            trigger={"type": "event", "event_name": "fire"},
            mode="background"
        )
        t2 = tm.create_task(
            "task2",
            trigger={"type": "event", "event_name": "other"},
            mode="background"
        )

        claimed = tm.claim_event_tasks("fire", now, limit=10)
        assert len(claimed) == 1
        assert claimed[0].id == t1.id
        assert claimed[0].status == "running"

    def test_completed_event_tasks_not_listed(self):
        """Test that completed event tasks don't stay in listener map."""
        tm = TaskManager()
        now = datetime.now()

        task = tm.create_task(
            "task",
            trigger={"type": "event", "event_name": "e"},
            mode="background"
        )

        task.transition_to("completed")
        tm._persist_tasks()

        mapping = tm.list_event_listener_map()
        assert "e" not in mapping or len(mapping.get("e", [])) == 0
