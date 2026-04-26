"""Task model for persistent execution tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4


TASK_STATUSES = {"pending", "running", "paused", "waiting_approval", "completed", "failed"}
TASK_MODES = {"foreground", "background"}
SCHEDULE_TYPES = {"immediate", "delayed", "recurring"}


@dataclass
class Task:
    """Persistent task entity."""

    goal: str
    status: str = "pending"
    steps: List[Dict[str, Any]] = field(default_factory=list)
    priority: int = 5
    mode: str = "foreground"
    schedule: Dict[str, Any] = field(default_factory=lambda: {"type": "immediate", "run_at": None, "interval": None})
    trigger: Optional[Dict[str, Any]] = None
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    retry_count: int = 0
    goal_id: Optional[str] = None
    requires_approval: bool = False
    approval_reasoning: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if self.status not in TASK_STATUSES:
            raise ValueError(f"Invalid task status: {self.status}")
        if self.mode not in TASK_MODES:
            raise ValueError(f"Invalid task mode: {self.mode}")
        self._normalize_schedule()
        self._normalize_trigger()
        if self.next_run_at is None:
            self.next_run_at = self._compute_initial_next_run()

    def touch(self):
        self.updated_at = datetime.now().isoformat()

    def transition_to(self, new_status: str):
        """Apply a safe lifecycle transition."""
        if new_status not in TASK_STATUSES:
            raise ValueError(f"Invalid task status: {new_status}")

        allowed = {
            "pending": {"running", "paused", "waiting_approval", "failed", "completed"},
            "running": {"paused", "completed", "failed", "pending", "waiting_approval"},
            "paused": {"pending", "running", "failed", "waiting_approval"},
            "waiting_approval": {"pending", "running", "failed", "completed"},
            "completed": {"pending"},
            "failed": {"pending"},
        }
        if new_status not in allowed[self.status]:
            raise ValueError(f"Invalid transition: {self.status} -> {new_status}")

        self.status = new_status
        self.touch()

    def update_steps(self, steps: List[Dict[str, Any]]):
        self.steps = steps
        self.touch()

    def is_event_driven(self) -> bool:
        return bool(self.trigger and self.trigger.get("type") == "event" and self.trigger.get("event_name"))

    def is_recurring(self) -> bool:
        return self.schedule.get("type") == "recurring"

    def due_at(self) -> Optional[datetime]:
        if self.is_event_driven():
            return None
        if self.next_run_at:
            return datetime.fromisoformat(self.next_run_at)
        return None

    def due_now(self, now: datetime) -> bool:
        if self.is_event_driven():
            return False
        due = self.due_at()
        return due is not None and due <= now

    def mark_run_started(self, now: Optional[datetime] = None):
        when = now or datetime.now()
        self.last_run_at = when.isoformat()
        self.touch()

    def mark_run_finished(self, success: bool, now: Optional[datetime] = None):
        when = now or datetime.now()
        if success:
            self.retry_count = 0
            if self.is_recurring():
                interval = int(self.schedule.get("interval", 0) or 0)
                if interval > 0:
                    self.next_run_at = (when + timedelta(seconds=interval)).isoformat()
                    self.transition_to("pending")
                else:
                    self.transition_to("failed")
            else:
                self.next_run_at = None
                self.transition_to("completed")
        else:
            self.retry_count += 1
        self.touch()

    def schedule_next_retry(self, delay_seconds: int, now: Optional[datetime] = None):
        when = now or datetime.now()
        self.next_run_at = (when + timedelta(seconds=delay_seconds)).isoformat()
        self.transition_to("pending")
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "steps": self.steps,
            "priority": self.priority,
            "mode": self.mode,
            "schedule": self.schedule,
            "trigger": self.trigger,
            "next_run_at": self.next_run_at,
            "last_run_at": self.last_run_at,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=data.get("id", str(uuid4())),
            goal=data.get("goal", ""),
            status=data.get("status", "pending"),
            steps=data.get("steps", []),
            priority=int(data.get("priority", 5)),
            mode=data.get("mode", "foreground"),
            schedule=data.get("schedule", {"type": "immediate", "run_at": None, "interval": None}),
            trigger=data.get("trigger"),
            next_run_at=data.get("next_run_at"),
            last_run_at=data.get("last_run_at"),
            retry_count=int(data.get("retry_count", 0)),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def _normalize_schedule(self):
        schedule = self.schedule or {}
        schedule_type = str(schedule.get("type", "immediate")).lower()
        if schedule_type not in SCHEDULE_TYPES:
            raise ValueError(f"Invalid schedule type: {schedule_type}")

        normalized = {
            "type": schedule_type,
            "run_at": schedule.get("run_at"),
            "interval": schedule.get("interval"),
        }

        if schedule_type == "delayed":
            run_at = normalized.get("run_at")
            if not run_at:
                raise ValueError("Delayed schedule requires run_at")
            datetime.fromisoformat(str(run_at))
            normalized["run_at"] = str(run_at)
            normalized["interval"] = None
        elif schedule_type == "recurring":
            interval = normalized.get("interval")
            if interval is None:
                raise ValueError("Recurring schedule requires interval")
            interval = int(interval)
            if interval <= 0:
                raise ValueError("Recurring interval must be positive")
            normalized["interval"] = interval
            normalized["run_at"] = None
        else:
            normalized["run_at"] = None
            normalized["interval"] = None

        self.schedule = normalized

    def _normalize_trigger(self):
        if not self.trigger:
            self.trigger = None
            return
        trigger_type = self.trigger.get("type")
        if trigger_type != "event":
            raise ValueError(f"Invalid trigger type: {trigger_type}")
        event_name = str(self.trigger.get("event_name", "")).strip()
        if not event_name:
            raise ValueError("Event trigger requires event_name")
        self.trigger = {"type": "event", "event_name": event_name}

    def _compute_initial_next_run(self) -> Optional[str]:
        if self.is_event_driven():
            return None
        schedule_type = self.schedule.get("type")
        if schedule_type == "immediate":
            return self.created_at
        if schedule_type == "delayed":
            return self.schedule.get("run_at")
        if schedule_type == "recurring":
            interval = int(self.schedule.get("interval", 0) or 0)
            if interval <= 0:
                return None
            return (datetime.fromisoformat(self.created_at) + timedelta(seconds=interval)).isoformat()
        return None
