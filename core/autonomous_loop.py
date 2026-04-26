"""Autonomous task generation and execution loop."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any

from core.decision_engine import DecisionEngine, AutonomousDecision
from core.tasks.task_manager import TaskManager


class AutonomousLoop:
    """Background loop for autonomous decision-making and task generation."""

    def __init__(
        self,
        decision_engine: DecisionEngine,
        task_manager: TaskManager,
        poll_interval: float = 60.0,
        max_tasks_per_hour: int = 5,
    ):
        self.decision_engine = decision_engine
        self.task_manager = task_manager
        self.poll_interval = float(poll_interval)
        self.max_tasks_per_hour = int(max_tasks_per_hour)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._enabled = False

        self._autonomous_tasks_created: list[str] = []
        self._decision_history: list[AutonomousDecision] = []
        self._on_decision_callback: Optional[Callable[[AutonomousDecision], None]] = None

    def start(self) -> None:
        """Start the autonomous loop."""
        with self._lock:
            if self._loop_thread and self._loop_thread.is_alive():
                return
            self._enabled = True
            self._stop_event.clear()
            self._loop_thread = threading.Thread(
                target=self._loop,
                daemon=True,
                name="jarvis-autonomous",
            )
            self._loop_thread.start()

    def stop(self) -> None:
        """Stop the autonomous loop."""
        with self._lock:
            self._enabled = False
        self._stop_event.set()
        thread = self._loop_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def enable(self) -> None:
        """Enable autonomous decision-making."""
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        """Disable autonomous decision-making."""
        with self._lock:
            self._enabled = False

    def is_enabled(self) -> bool:
        """Check if autonomy is enabled."""
        with self._lock:
            return self._enabled

    def set_decision_callback(self, callback: Callable[[AutonomousDecision], None]) -> None:
        """Set callback for decision events."""
        with self._lock:
            self._on_decision_callback = callback

    def get_recent_decisions(self, limit: int = 10) -> list[Dict[str, Any]]:
        """Get recent autonomous decisions."""
        with self._lock:
            return [d.to_dict() for d in self._decision_history[-limit:]]

    def get_created_tasks(self) -> list[str]:
        """Get list of autonomously created task IDs."""
        with self._lock:
            return list(self._autonomous_tasks_created)

    def _loop(self) -> None:
        """Main autonomous loop."""
        while not self._stop_event.is_set():
            if self._enabled:
                self._evaluate_and_act()

            self._stop_event.wait(timeout=self.poll_interval)

    def _evaluate_and_act(self) -> None:
        """Evaluate context and create task if decision warrants it."""
        try:
            decision = self.decision_engine.decide()

            with self._lock:
                self._decision_history.append(decision)
                if len(self._decision_history) > 100:
                    self._decision_history.pop(0)

                if self._on_decision_callback:
                    try:
                        self._on_decision_callback(decision)
                    except Exception:
                        pass

            if decision.should_act and decision.confidence >= self.decision_engine.confidence_threshold:
                self._maybe_create_task(decision)
        except Exception:
            pass

    def _maybe_create_task(self, decision: AutonomousDecision) -> None:
        """Create a task if guardrails allow it (async approval)."""
        if not decision.proposed_task:
            return

        if not self._check_rate_limit():
            return

        if self._is_duplicate_task(decision.proposed_task, decision.goal_id):
            return

        try:
            task = self.task_manager.create_task(
                goal=decision.proposed_task.get("goal", "autonomous task"),
                mode=decision.proposed_task.get("mode", "background"),
                priority=int(decision.proposed_task.get("priority", 5)),
                goal_id=decision.goal_id,
                requires_approval=decision.requires_approval,
                approval_reasoning=decision.reason if decision.requires_approval else None,
            )

            if decision.requires_approval:
                self.task_manager.set_task_approval_needed(task.id, decision.reason)

            with self._lock:
                self._autonomous_tasks_created.append(task.id)
        except Exception:
            pass

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        with self._lock:
            now = datetime.now()
            hour_ago = now - timedelta(hours=1)

            recent = 0
            for task_id in self._autonomous_tasks_created:
                task = self.task_manager.get_task(task_id)
                if task and task.created_at:
                    try:
                        created = datetime.fromisoformat(task.created_at)
                        if created >= hour_ago:
                            recent += 1
                    except ValueError:
                        pass

            return recent < self.max_tasks_per_hour

    def _is_duplicate_task(self, proposed: Dict[str, Any], goal_id: Optional[str] = None) -> bool:
        """Check if similar task already exists (goal-aware)."""
        goal = proposed.get("goal", "").lower()
        if not goal:
            return False

        existing_tasks = self.task_manager.list_tasks()
        for task in existing_tasks:
            if task.status in {"running", "pending"}:
                if task.goal.lower() == goal:
                    if goal_id is None or task.goal_id == goal_id:
                        return True

                if self._goal_similarity(task.goal.lower(), goal) > 0.8:
                    if goal_id is None or task.goal_id == goal_id:
                        return True

        return False

    @staticmethod
    def _goal_similarity(goal1: str, goal2: str) -> float:
        """Simple string similarity metric."""
        common = sum(1 for c in goal1 if c in goal2)
        total = max(len(goal1), len(goal2))
        return common / total if total > 0 else 0.0
