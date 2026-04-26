"""Tests for persistent task management and background execution."""

import tempfile
import time
from pathlib import Path

from core.tasks.task import Task
from core.tasks.task_manager import TaskManager


class TestTaskModel:
    def test_task_serialization_round_trip(self):
        task = Task(goal="run diagnostics", mode="background")
        data = task.to_dict()
        restored = Task.from_dict(data)

        assert restored.id == task.id
        assert restored.goal == "run diagnostics"
        assert restored.mode == "background"

    def test_task_transitions(self):
        task = Task(goal="x")
        task.transition_to("running")
        task.transition_to("paused")
        task.transition_to("pending")
        assert task.status == "pending"


class TestTaskManager:
    def test_persistence_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"
            manager = TaskManager(storage_path=str(path))
            created = manager.create_task("collect logs", mode="background")

            reloaded = TaskManager(storage_path=str(path))
            loaded = reloaded.get_task(created.id)

            assert loaded is not None
            assert loaded.goal == "collect logs"
            assert path.exists()

    def test_running_tasks_resume_as_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"
            manager = TaskManager(storage_path=str(path))
            task = manager.create_task("resume me", mode="background")
            manager.mark_task_running(task.id)

            reloaded = TaskManager(storage_path=str(path))
            loaded = reloaded.get_task(task.id)
            assert loaded is not None
            assert loaded.status == "pending"

    def test_background_worker_executes_pending_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"
            manager = TaskManager(storage_path=str(path))
            task = manager.create_task("bg run", mode="background")

            def worker(task_obj):
                manager.set_task_steps(task_obj.id, [{"id": 1, "status": "success"}])
                return True

            manager.start_background_worker(worker)
            for _ in range(30):
                current = manager.get_task(task.id)
                if current and current.status == "completed":
                    break
                time.sleep(0.1)
            manager.stop_background_worker()

            final_task = manager.get_task(task.id)
            assert final_task is not None
            assert final_task.status == "completed"
            assert len(final_task.steps) == 1
