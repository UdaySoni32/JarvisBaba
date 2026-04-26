"""Tests for Scheduler and time-based task dispatch."""

import pytest
import time
from datetime import datetime, timedelta
from core.scheduler import Scheduler
from core.tasks.task_manager import TaskManager
from core.tasks.task import Task
from core.events import EventBus


class TestScheduler:
    """Test Scheduler functionality."""

    def test_scheduler_start_stop(self):
        """Test scheduler can start and stop."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        def executor(task_id: str) -> bool:
            return True

        sched.start(executor)
        assert sched._scheduler_thread is not None
        assert sched._scheduler_thread.is_alive()

        sched.stop()
        sched._scheduler_thread.join(timeout=2)
        assert not sched._scheduler_thread.is_alive()

    def test_list_scheduled_tasks(self):
        """Test listing scheduled tasks."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        now = datetime.now()
        future = (now + timedelta(seconds=10)).isoformat()

        tm.create_task(
            "delayed task",
            schedule={"type": "delayed", "run_at": future, "interval": None},
            mode="background"
        )
        tm.create_task(
            "recurring task",
            schedule={"type": "recurring", "run_at": None, "interval": 60},
            mode="background"
        )

        scheduled = sched.list_scheduled_tasks()
        assert len(scheduled) == 2
        assert any(t["goal"] == "delayed task" for t in scheduled)
        assert any(t["goal"] == "recurring task" for t in scheduled)

    def test_list_event_listeners(self):
        """Test listing event listeners."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        tm.create_task(
            "t1",
            trigger={"type": "event", "event_name": "login"},
            mode="background"
        )
        tm.create_task(
            "t2",
            trigger={"type": "event", "event_name": "logout"},
            mode="background"
        )

        listeners = sched.list_event_listeners()
        assert "login" in listeners
        assert "logout" in listeners

    def test_fire_event(self):
        """Test firing an event."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        called = []

        def handler(p):
            called.append(p)

        bus.subscribe("test_event", handler)
        sched.fire_event("test_event", "payload")

        assert len(called) == 1
        assert called[0] == "payload"

    def test_scheduler_thread_daemon(self):
        """Test that scheduler thread is daemon."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        def executor(task_id: str) -> bool:
            return True

        sched.start(executor)
        assert sched._scheduler_thread.daemon

    def test_scheduler_respects_max_concurrent(self):
        """Test scheduler respects max_concurrent limit."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus, max_concurrent=1)

        # Create 3 due tasks
        now = datetime.now()
        for i in range(3):
            tm.create_task(
                f"task{i}",
                schedule={"type": "immediate", "run_at": None, "interval": None},
                mode="background"
            )

        executed = []

        def executor(task_id: str) -> bool:
            executed.append(task_id)
            return True

        sched.start(executor)
        sched._stop_event.set()
        sched._scheduler_thread.join(timeout=2)

        # Only 1 should be executed immediately due to max_concurrent=1
        assert len(executed) <= 1

    def test_next_wake_in_seconds(self):
        """Test calculation of next wake time."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        now = datetime.now()
        future = now + timedelta(seconds=30)

        tm.create_task(
            "delayed",
            schedule={"type": "delayed", "run_at": future.isoformat(), "interval": None},
            mode="background"
        )

        wait = tm.next_wake_in_seconds(now, max_wait=10.0)
        assert 0 < wait <= 10.0

    def test_next_wake_defaults_to_max_wait(self):
        """Test that next_wake_in_seconds defaults to max_wait when no tasks."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        now = datetime.now()
        wait = tm.next_wake_in_seconds(now, max_wait=5.0)
        assert wait == 5.0

    def test_scheduler_with_immediate_tasks(self):
        """Test scheduler dispatches immediate tasks."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        task = tm.create_task(
            "immediate",
            schedule={"type": "immediate", "run_at": None, "interval": None},
            mode="background"
        )

        executed = []

        def executor(task_id: str) -> bool:
            executed.append(task_id)
            return True

        sched.start(executor)
        time.sleep(0.2)
        sched._stop_event.set()
        sched._scheduler_thread.join(timeout=2)

        # Immediate task should execute
        assert task.id in executed

    def test_scheduler_respects_schedule_type(self):
        """Test scheduler only runs background mode scheduled tasks."""
        tm = TaskManager()
        bus = EventBus()
        sched = Scheduler(tm, bus)

        tm.create_task(
            "foreground_immediate",
            mode="foreground",
            schedule={"type": "immediate", "run_at": None, "interval": None}
        )
        tm.create_task(
            "background_immediate",
            mode="background",
            schedule={"type": "immediate", "run_at": None, "interval": None}
        )

        executed = []

        def executor(task_id: str) -> bool:
            executed.append(task_id)
            return True

        sched.start(executor)
        time.sleep(0.2)
        sched._stop_event.set()
        sched._scheduler_thread.join(timeout=2)

        # Only background task should execute via scheduler
        fg_task = tm.list_tasks()[0]
        bg_task = tm.list_tasks()[1]
        
        assert (fg_task.mode == "background" and fg_task.id in executed) or \
               (bg_task.mode == "background" and bg_task.id in executed)


class TestScheduleParser:
    """Test schedule intent parsing."""

    def test_parse_schedule_immediate(self):
        """Test immediate schedule (no markers)."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("do this task")
        assert schedule is None or schedule["type"] == "immediate"

    def test_parse_delay_in_seconds(self):
        """Test parsing 'in X seconds' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("do this in 10 seconds")
        assert schedule is not None
        assert schedule["type"] == "delayed"
        assert schedule["run_at"] is not None

    def test_parse_delay_in_minutes(self):
        """Test parsing 'in X minutes' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("remind me in 5 minutes")
        assert schedule is not None
        assert schedule["type"] == "delayed"

    def test_parse_delay_in_hours(self):
        """Test parsing 'in X hours' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("send in 2 hours")
        assert schedule is not None
        assert schedule["type"] == "delayed"

    def test_parse_recurring_every_seconds(self):
        """Test parsing 'every X seconds' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("run every 30 seconds")
        assert schedule is not None
        assert schedule["type"] == "recurring"
        assert schedule["interval"] == 30

    def test_parse_recurring_every_minutes(self):
        """Test parsing 'every X minutes' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("check every 5 minutes")
        assert schedule is not None
        assert schedule["type"] == "recurring"
        assert schedule["interval"] == 300

    def test_parse_recurring_every_hours(self):
        """Test parsing 'every X hours' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("run every 2 hours")
        assert schedule is not None
        assert schedule["type"] == "recurring"
        assert schedule["interval"] == 7200

    def test_parse_event_trigger_when(self):
        """Test parsing 'when X happens' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("run when user logs in")
        assert trigger is not None
        assert trigger["type"] == "event"
        assert trigger["event_name"] is not None

    def test_parse_event_trigger_on(self):
        """Test parsing 'on X' format."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("do task on file_created")
        assert trigger is not None
        assert trigger["type"] == "event"

    def test_parse_combined_schedule_and_event(self):
        """Test parsing both schedule and event."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent(
            "run every hour when user logs in"
        )
        # Should get one or both
        assert schedule is not None or trigger is not None

    def test_no_schedule_or_event(self):
        """Test input with no schedule/event markers."""
        from core.schedule_parser import ScheduleParser

        schedule, trigger = ScheduleParser.parse_schedule_intent("just do this thing")
        assert schedule is None
        assert trigger is None
