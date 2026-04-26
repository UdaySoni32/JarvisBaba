"""Persistent and thread-safe task orchestration with scheduling semantics."""

from __future__ import annotations

import heapq
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.tasks.task import Task


class TaskManager:
    """Owns persistence, lifecycle transitions, and task dispatch selection."""

    AGE_BOOST_SECONDS = 120.0

    def __init__(
        self,
        storage_path: Optional[str] = None,
        queue_size_limit: int = 1000,
        max_global_retries: int = 3,
    ):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
                "tasks.json",
            )

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self.queue_size_limit = int(queue_size_limit)
        self.max_global_retries = int(max_global_retries)

        self._lock = threading.RLock()
        self._tasks: Dict[str, Task] = {}
        self._active_execution: Dict[str, Dict] = {}
        self._last_dispatch_at: Dict[str, float] = {}

        self._load_tasks()

    def create_task(
        self,
        goal: str,
        mode: str = "foreground",
        priority: int = 5,
        steps: Optional[List[Dict]] = None,
        schedule: Optional[Dict] = None,
        trigger: Optional[Dict] = None,
    ) -> Task:
        with self._lock:
            if self._active_task_count() >= self.queue_size_limit:
                raise ValueError(f"Queue size limit exceeded ({self.queue_size_limit})")

            task = Task(
                goal=goal,
                mode=mode,
                priority=priority,
                steps=steps or [],
                schedule=schedule or {"type": "immediate", "run_at": None, "interval": None},
                trigger=trigger,
            )
            self._tasks[task.id] = task
            self._persist_tasks()
            return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: (-t.priority, t.created_at))

    def list_scheduled_tasks(self) -> List[Task]:
        with self._lock:
            return sorted(
                [t for t in self._tasks.values() if t.schedule.get("type") in {"delayed", "recurring"}],
                key=lambda t: (t.next_run_at or "", -t.priority),
            )

    def list_event_listener_map(self) -> Dict[str, List[str]]:
        with self._lock:
            mapping: Dict[str, List[str]] = {}
            for task in self._tasks.values():
                if task.status in {"completed", "failed"}:
                    continue
                if task.trigger and task.trigger.get("type") == "event":
                    name = task.trigger.get("event_name")
                    mapping.setdefault(name, []).append(task.id)
            return mapping

    def set_task_steps(self, task_id: str, steps: List[Dict]):
        with self._lock:
            task = self._require_task(task_id)
            task.update_steps(steps)
            self._persist_tasks()

    def mark_task_running(self, task_id: str):
        with self._lock:
            task = self._require_task(task_id)
            if task.status in {"pending", "paused", "completed", "failed"}:
                task.transition_to("running")
                task.mark_run_started()
                self._persist_tasks()

    def mark_task_completed(self, task_id: str):
        with self._lock:
            task = self._require_task(task_id)
            if task.status == "running":
                task.mark_run_finished(True)
                self._active_execution.pop(task_id, None)
                self._persist_tasks()

    def mark_task_failed(self, task_id: str, reason: Optional[str] = None):
        with self._lock:
            task = self._require_task(task_id)
            if task.status in {"pending", "running", "paused", "completed", "failed"}:
                if task.status != "running":
                    task.transition_to("running")
                task.mark_run_finished(False)
                if reason:
                    task.steps.append({"id": "task-error", "status": "failed", "error": reason})
                self._active_execution.pop(task_id, None)
                self._persist_tasks()

    def pause_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._require_task(task_id)
            if task.status not in {"pending", "running"}:
                return False
            task.transition_to("paused")
            self._active_execution.pop(task_id, None)
            self._persist_tasks()
            return True

    def resume_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._require_task(task_id)
            if task.status != "paused":
                return False
            task.transition_to("pending")
            self._persist_tasks()
            return True

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._require_task(task_id)
            if task.status in {"completed", "failed"}:
                return False
            if task.status == "running":
                self._active_execution.pop(task_id, None)
            task.transition_to("failed")
            task.steps.append(
                {"id": "task-cancelled", "status": "failed", "error": "Task cancelled by user"}
            )
            self._persist_tasks()
            return True

    def set_active_execution(self, task_id: str, data: Dict):
        with self._lock:
            self._active_execution[task_id] = data

    def clear_active_execution(self, task_id: str):
        with self._lock:
            self._active_execution.pop(task_id, None)

    def get_active_execution(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._active_execution)

    def claim_due_tasks(
        self,
        now: datetime,
        limit: int,
        eligible_modes: Optional[Iterable[str]] = None,
    ) -> List[Task]:
        with self._lock:
            if limit <= 0:
                return []
            modes = set(eligible_modes or ["background"])
            pending_due = [
                t for t in self._tasks.values()
                if t.mode in modes and t.status == "pending" and not t.is_event_driven() and t.due_now(now)
            ]
            return self._claim_with_priority_and_fairness(pending_due, now, limit)

    def claim_event_tasks(self, event_name: str, now: datetime, limit: int) -> List[Task]:
        with self._lock:
            if limit <= 0:
                return []
            pending_event = [
                t for t in self._tasks.values()
                if t.status == "pending"
                and t.mode == "background"
                and t.trigger
                and t.trigger.get("type") == "event"
                and t.trigger.get("event_name") == event_name
            ]
            return self._claim_with_priority_and_fairness(pending_event, now, limit)

    def next_wake_in_seconds(self, now: datetime, max_wait: float = 5.0) -> float:
        with self._lock:
            due_times = [
                t.due_at() for t in self._tasks.values()
                if t.status == "pending" and t.mode == "background" and not t.is_event_driven() and t.due_at()
            ]
            if not due_times:
                return max_wait
            nearest = min(due_times)
            delta = (nearest - now).total_seconds()
            return max(0.0, min(max_wait, delta))

    def finalize_execution(self, task_id: str, success: bool, error: Optional[str] = None) -> Dict[str, str]:
        """Finalize execution with retry and recurring semantics."""
        with self._lock:
            task = self._require_task(task_id)
            if task.status != "running":
                return {"status": task.status, "reason": "already-finalized"}

            now = datetime.now()
            if success:
                task.mark_run_finished(True, now=now)
                outcome = {"status": task.status, "reason": "success"}
            else:
                task.mark_run_finished(False, now=now)
                if task.retry_count <= self.max_global_retries:
                    backoff = min(60, 2 ** max(task.retry_count - 1, 0))
                    task.schedule_next_retry(backoff, now=now)
                    if error:
                        task.steps.append(
                            {"id": "task-retry", "status": "pending", "error": error, "retry": task.retry_count}
                        )
                    outcome = {"status": "pending", "reason": "retry_scheduled"}
                else:
                    task.transition_to("failed")
                    if error:
                        task.steps.append({"id": "task-error", "status": "failed", "error": error})
                    outcome = {"status": "failed", "reason": "max_retries_exceeded"}

            self._active_execution.pop(task_id, None)
            self._persist_tasks()
            return outcome

    def _claim_with_priority_and_fairness(self, candidates: List[Task], now: datetime, limit: int) -> List[Task]:
        heap = []
        now_ts = now.timestamp()
        for task in candidates:
            age_seconds = max(0.0, now_ts - datetime.fromisoformat(task.created_at).timestamp())
            aging_boost = age_seconds / self.AGE_BOOST_SECONDS
            effective_priority = float(task.priority) + aging_boost
            last_dispatched = self._last_dispatch_at.get(task.id, 0.0)
            # max-heap behavior via negative values
            heapq.heappush(heap, (-effective_priority, last_dispatched, task.created_at, task.id))

        claimed: List[Task] = []
        while heap and len(claimed) < limit:
            _, _, _, task_id = heapq.heappop(heap)
            task = self._tasks.get(task_id)
            if not task or task.status != "pending":
                continue
            task.transition_to("running")
            task.mark_run_started(now)
            self._last_dispatch_at[task.id] = now_ts
            claimed.append(task)

        if claimed:
            self._persist_tasks()
        return claimed

    def _active_task_count(self) -> int:
        return len([t for t in self._tasks.values() if t.status not in {"completed", "failed"}])

    def _load_tasks(self):
        if not self.storage_path.exists():
            self._persist_tasks()
            return

        with self.storage_path.open("r", encoding="utf-8") as f:
            raw = f.read().strip()

        if not raw:
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            corrupt = self.storage_path.with_suffix(self.storage_path.suffix + ".corrupt")
            os.replace(self.storage_path, corrupt)
            self._tasks = {}
            self._persist_tasks()
            return

        loaded_tasks = data.get("tasks", [])
        with self._lock:
            for item in loaded_tasks:
                task = Task.from_dict(item)
                if task.status == "running":
                    task.status = "pending"
                    task.touch()
                self._tasks[task.id] = task
            self._persist_tasks()

    def _persist_tasks(self):
        payload = {"tasks": [t.to_dict() for t in self._tasks.values()]}
        tmp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.storage_path)

    def _require_task(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        return task
