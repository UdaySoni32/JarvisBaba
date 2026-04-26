"""Goal model for hierarchical objective tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4


GOAL_STATUSES = {"active", "paused", "completed", "failed"}


@dataclass
class Goal:
    """Persistent goal entity with hierarchy support."""

    description: str
    priority: int = 5
    status: str = "active"
    success_criteria: Optional[str] = None
    parent_goal_id: Optional[str] = None
    task_ids: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if self.status not in GOAL_STATUSES:
            raise ValueError(f"Invalid goal status: {self.status}")
        if not (1 <= self.priority <= 10):
            raise ValueError(f"Priority must be 1-10, got {self.priority}")

    def touch(self):
        """Update modification timestamp."""
        self.updated_at = datetime.now().isoformat()

    def add_task(self, task_id: str):
        """Link a task to this goal."""
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)
            self.touch()

    def remove_task(self, task_id: str):
        """Unlink a task from this goal."""
        if task_id in self.task_ids:
            self.task_ids.remove(task_id)
            self.touch()

    def transition_to(self, new_status: str):
        """Apply safe status transition."""
        if new_status not in GOAL_STATUSES:
            raise ValueError(f"Invalid goal status: {new_status}")

        allowed = {
            "active": {"paused", "completed", "failed"},
            "paused": {"active", "failed", "completed"},
            "completed": {"active"},
            "failed": {"active"},
        }
        if new_status not in allowed[self.status]:
            raise ValueError(f"Invalid transition: {self.status} -> {new_status}")

        self.status = new_status
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "success_criteria": self.success_criteria,
            "parent_goal_id": self.parent_goal_id,
            "task_ids": self.task_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Goal:
        """Create from JSON dict."""
        return Goal(
            id=data.get("id", str(uuid4())),
            description=data["description"],
            priority=data.get("priority", 5),
            status=data.get("status", "active"),
            success_criteria=data.get("success_criteria"),
            parent_goal_id=data.get("parent_goal_id"),
            task_ids=data.get("task_ids", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
