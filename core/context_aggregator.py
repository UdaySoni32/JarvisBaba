"""Context aggregation for autonomous decision-making."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from core.events import EventBus
from core.tasks.task_manager import TaskManager


class ContextAggregator:
    """Collects system state for autonomous decision-making."""

    def __init__(self, task_manager: TaskManager, event_bus: EventBus):
        self.task_manager = task_manager
        self.event_bus = event_bus
        self._lock = threading.RLock()

    def get_context(self, time_window_seconds: int = 300) -> Dict[str, Any]:
        """
        Aggregate current system context.

        time_window_seconds: Look back this far for events and task history
        """
        with self._lock:
            now = datetime.now()
            window_start = now - timedelta(seconds=time_window_seconds)

            return {
                "timestamp": now.isoformat(),
                "recent_events": self._get_recent_events(window_start),
                "task_summary": self._get_task_summary(),
                "failed_tasks": self._get_failed_tasks(window_start),
                "active_tasks": self._get_active_tasks(),
                "recurring_patterns": self._detect_patterns(),
            }

    def _get_recent_events(self, since: datetime) -> List[Dict[str, Any]]:
        """Get recent events from event bus history."""
        recent = self.event_bus.recent_events(limit=50)
        return [
            {
                "event": e["event"],
                "payload": e["payload"],
                "timestamp": datetime.now().isoformat(),  # Approximate
            }
            for e in recent
        ]

    def _get_task_summary(self) -> Dict[str, int]:
        """Count tasks by status."""
        tasks = self.task_manager.list_tasks()
        summary = {}
        for task in tasks:
            status = task.status
            summary[status] = summary.get(status, 0) + 1
        return summary

    def _get_failed_tasks(self, since: datetime) -> List[Dict[str, Any]]:
        """Get recently failed tasks."""
        all_tasks = self.task_manager.list_tasks()
        failed = []
        for task in all_tasks:
            if task.status == "failed":
                try:
                    updated = datetime.fromisoformat(task.updated_at)
                    if updated >= since:
                        failed.append(
                            {
                                "id": task.id,
                                "goal": task.goal,
                                "updated_at": task.updated_at,
                                "retry_count": task.retry_count,
                            }
                        )
                except (ValueError, AttributeError):
                    pass
        return failed

    def _get_active_tasks(self) -> List[Dict[str, str]]:
        """Get currently running/pending tasks."""
        all_tasks = self.task_manager.list_tasks()
        active = []
        for task in all_tasks:
            if task.status in {"running", "pending"}:
                active.append(
                    {
                        "id": task.id[:8],
                        "goal": task.goal[:40],
                        "status": task.status,
                        "priority": str(task.priority),
                    }
                )
        return active[:10]  # Limit to 10 most recent

    def _detect_patterns(self) -> Dict[str, Any]:
        """Detect recurring patterns in task execution."""
        all_tasks = self.task_manager.list_tasks()
        recurring_tasks = [t for t in all_tasks if t.is_recurring()]
        failed_count = len([t for t in all_tasks if t.status == "failed"])
        completed_count = len([t for t in all_tasks if t.status == "completed"])

        return {
            "recurring_task_count": len(recurring_tasks),
            "failed_task_count": failed_count,
            "completed_task_count": completed_count,
            "has_failures": failed_count > 0,
            "high_completion_rate": completed_count > failed_count * 2 if failed_count > 0 else True,
        }

    def get_autonomy_state(self) -> Dict[str, Any]:
        """Get state relevant for autonomy decisions."""
        return {
            "context": self.get_context(),
            "event_listeners": self.event_bus.all_events(),
            "event_history": self.event_bus.recent_events(limit=20),
        }
