"""Goal lifecycle management with persistence."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.goals.goal import Goal, GOAL_STATUSES


class GoalManager:
    """Manages goal hierarchy, persistence, and task linkage."""

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
                "goals.json",
            )

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._goals: Dict[str, Goal] = {}

        self._load_goals()

    def create_goal(
        self,
        description: str,
        priority: int = 5,
        success_criteria: Optional[str] = None,
        parent_goal_id: Optional[str] = None,
    ) -> Goal:
        """Create a new goal."""
        with self._lock:
            if parent_goal_id and parent_goal_id not in self._goals:
                raise ValueError(f"Parent goal {parent_goal_id} not found")

            goal = Goal(
                description=description,
                priority=priority,
                status="active",
                success_criteria=success_criteria,
                parent_goal_id=parent_goal_id,
            )

            self._goals[goal.id] = goal
            self._persist_goals()
            return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID."""
        with self._lock:
            return self._goals.get(goal_id)

    def list_goals(self, status: Optional[str] = None) -> List[Goal]:
        """List all goals, optionally filtered by status."""
        with self._lock:
            goals = list(self._goals.values())
            if status:
                goals = [g for g in goals if g.status == status]
            return sorted(goals, key=lambda g: g.priority, reverse=True)

    def list_active_goals(self) -> List[Goal]:
        """List all active goals."""
        return self.list_goals(status="active")

    def list_subgoals(self, parent_goal_id: str) -> List[Goal]:
        """List all subgoals of a goal."""
        with self._lock:
            return [g for g in self._goals.values() if g.parent_goal_id == parent_goal_id]

    def link_task_to_goal(self, goal_id: str, task_id: str):
        """Link a task to a goal."""
        with self._lock:
            goal = self._require_goal(goal_id)
            goal.add_task(task_id)
            self._persist_goals()

    def unlink_task_from_goal(self, goal_id: str, task_id: str):
        """Unlink a task from a goal."""
        with self._lock:
            goal = self._require_goal(goal_id)
            goal.remove_task(task_id)
            self._persist_goals()

    def get_tasks_for_goal(self, goal_id: str) -> List[str]:
        """Get all task IDs for a goal."""
        with self._lock:
            goal = self._require_goal(goal_id)
            return goal.task_ids.copy()

    def pause_goal(self, goal_id: str):
        """Pause a goal (prevents new task creation)."""
        with self._lock:
            goal = self._require_goal(goal_id)
            goal.transition_to("paused")
            self._persist_goals()

    def resume_goal(self, goal_id: str):
        """Resume a paused goal."""
        with self._lock:
            goal = self._require_goal(goal_id)
            goal.transition_to("active")
            self._persist_goals()

    def complete_goal(self, goal_id: str):
        """Mark a goal as completed."""
        with self._lock:
            goal = self._require_goal(goal_id)
            goal.transition_to("completed")
            self._persist_goals()

    def fail_goal(self, goal_id: str):
        """Mark a goal as failed."""
        with self._lock:
            goal = self._require_goal(goal_id)
            goal.transition_to("failed")
            self._persist_goals()

    def update_goal_priority(self, goal_id: str, priority: int):
        """Update goal priority."""
        if not (1 <= priority <= 10):
            raise ValueError(f"Priority must be 1-10, got {priority}")

        with self._lock:
            goal = self._require_goal(goal_id)
            goal.priority = priority
            goal.touch()
            self._persist_goals()

    def _require_goal(self, goal_id: str) -> Goal:
        """Get goal or raise error."""
        goal = self._goals.get(goal_id)
        if not goal:
            raise ValueError(f"Goal {goal_id} not found")
        return goal

    def _load_goals(self):
        """Load goals from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                for goal_data in data:
                    goal = Goal.from_dict(goal_data)
                    self._goals[goal.id] = goal
        except (json.JSONDecodeError, IOError) as e:
            pass

    def _persist_goals(self):
        """Persist goals to disk."""
        try:
            data = [goal.to_dict() for goal in self._goals.values()]
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            pass
