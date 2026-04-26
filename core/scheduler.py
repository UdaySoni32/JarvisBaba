"""Task scheduler with time-based and event-based dispatch."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from core.events.event_bus import EventBus
from core.tasks.task_manager import TaskManager


class Scheduler:
    """Monitors and dispatches tasks based on schedule and events."""

    def __init__(
        self,
        task_manager: TaskManager,
        event_bus: EventBus,
        max_concurrent: int = 5,
        poll_interval: float = 1.0,
    ):
        self.task_manager = task_manager
        self.event_bus = event_bus
        self.max_concurrent = int(max_concurrent)
        self.poll_interval = float(poll_interval)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._task_executor: Optional[Callable] = None

        self._register_event_subscriptions()

    def start(self, task_executor: Callable[[str], bool]) -> None:
        """Start the scheduler and register task executor callback."""
        with self._lock:
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                return
            self._task_executor = task_executor
            self._stop_event.clear()
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="jarvis-scheduler",
            )
            self._scheduler_thread.start()

    def stop(self) -> None:
        """Stop the scheduler."""
        self._stop_event.set()
        thread = self._scheduler_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def fire_event(self, event_name: str, payload: Optional[str] = None) -> None:
        """Publish an event via the bus (triggers event-driven tasks)."""
        self.event_bus.publish(event_name, payload)

    def list_scheduled_tasks(self) -> List[Dict]:
        """Get scheduled tasks with next run times."""
        return [
            {
                "id": t.id,
                "goal": t.goal,
                "status": t.status,
                "next_run_at": t.next_run_at,
                "interval_seconds": t.schedule.get("interval"),
                "recurring": t.is_recurring(),
            }
            for t in self.task_manager.list_scheduled_tasks()
        ]

    def list_event_listeners(self) -> Dict[str, List[str]]:
        """Get event -> task_id mappings."""
        return self.task_manager.list_event_listener_map()

    def _scheduler_loop(self) -> None:
        """Main scheduler loop: dispatch due tasks and handle events."""
        while not self._stop_event.is_set():
            now = datetime.now()
            try:
                due_tasks = self.task_manager.claim_due_tasks(
                    now, limit=self.max_concurrent, eligible_modes=["background"]
                )
                for task in due_tasks:
                    if self._task_executor:
                        try:
                            self._task_executor(task.id)
                        except Exception:
                            pass
            except Exception:
                pass

            wait_time = self.task_manager.next_wake_in_seconds(now, max_wait=self.poll_interval)
            self._stop_event.wait(timeout=wait_time)

    def _register_event_subscriptions(self) -> None:
        """Subscribe scheduler to all event-driven tasks using a dynamic handler."""

        def universal_event_handler(payload: str) -> None:
            """Universal handler that checks task map for matching events."""
            # This handler is called for any event; we'll check what events are needed
            now = datetime.now()
            event_map = self.task_manager.list_event_listener_map()
            
            # Get the event name from context (this is a limitation of the simple event bus)
            # For now, we'll just check all pending event tasks
            for task in self.task_manager._tasks.values():
                if (task.status == "pending" and 
                    task.mode == "background" and 
                    task.is_event_driven()):
                    # Claim and execute this event task
                    if self._task_executor:
                        try:
                            self._task_executor(task.id)
                        except Exception:
                            pass

        # Instead, we need to make the event bus smarter
        # Let's update to register handlers per event name dynamically
        event_map = self.task_manager.list_event_listener_map()
        for event_name in event_map:
            def make_handler(evt_name: str) -> Callable[[str], None]:
                def handler(payload: str) -> None:
                    now = datetime.now()
                    tasks = self.task_manager.claim_event_tasks(evt_name, now, limit=self.max_concurrent)
                    for task in tasks:
                        if self._task_executor:
                            try:
                                self._task_executor(task.id)
                            except Exception:
                                pass
                return handler
            
            self.event_bus.subscribe(event_name, make_handler(event_name))
