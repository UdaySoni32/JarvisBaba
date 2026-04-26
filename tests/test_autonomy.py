"""Tests for autonomous decision-making and task generation."""

import tempfile
import os
from datetime import datetime
from core.context_aggregator import ContextAggregator
from core.decision_engine import DecisionEngine, AutonomousDecision
from core.autonomous_loop import AutonomousLoop
from core.tasks.task_manager import TaskManager
from core.events import EventBus
from models.llm import LLMFactory


class TestContextAggregator:
    """Test context collection for autonomy."""

    def test_context_aggregation(self):
        """Test basic context aggregation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)

            context = agg.get_context()

            assert "timestamp" in context
            assert "recent_events" in context
            assert "task_summary" in context
            assert "failed_tasks" in context
            assert "active_tasks" in context
            assert "recurring_patterns" in context

    def test_task_summary(self):
        """Test task summary counting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)

            tm.create_task("t1", mode="background")
            tm.create_task("t2", mode="background")

            context = agg.get_context()
            summary = context["task_summary"]

            assert summary.get("pending") >= 2

    def test_failed_tasks_detection(self):
        """Test detection of failed tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)

            task = tm.create_task("failing", mode="background")
            tm.mark_task_running(task.id)
            tm.finalize_execution(task.id, success=False)

            context = agg.get_context()
            failed = context["failed_tasks"]

            assert len(failed) > 0

    def test_autonomy_state(self):
        """Test autonomy state retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)

            state = agg.get_autonomy_state()

            assert "context" in state
            assert "event_listeners" in state
            assert "event_history" in state


class TestDecisionEngine:
    """Test autonomous decision-making."""

    def test_heuristic_no_action(self):
        """Test that system at rest recommends no action."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None, confidence_threshold=0.7)

            decision = engine.decide()

            assert isinstance(decision, AutonomousDecision)
            assert "reason" in decision.to_dict()

    def test_heuristic_failure_detection(self):
        """Test detection of failures triggers decision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None, confidence_threshold=0.5)

            task = tm.create_task("fail_task", mode="background")
            tm.mark_task_running(task.id)
            tm.finalize_execution(task.id, success=False)

            decision = engine.decide()

            assert decision.should_act
            assert decision.confidence > 0.5

    def test_decision_dict_conversion(self):
        """Test decision can be converted to dict."""
        decision = AutonomousDecision(
            should_act=True,
            reason="test",
            confidence=0.8,
            proposed_task={"goal": "test", "priority": 5}
        )

        d = decision.to_dict()
        assert d["should_act"] is True
        assert d["confidence"] == 0.8
        assert "proposed_task" in d

    def test_llm_response_parsing(self):
        """Test LLM response parsing."""
        import json
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None)

            response = json.dumps({
                "should_act": True,
                "reason": "test reason",
                "confidence": 0.85,
                "proposed_task": {"goal": "test", "priority": 7}
            })

            parsed = engine._parse_llm_response(response)

            assert parsed["should_act"] is True
            assert parsed["confidence"] == 0.85


class TestAutonomousLoop:
    """Test autonomous execution loop."""

    def test_loop_start_stop(self):
        """Test loop can start and stop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None)
            loop = AutonomousLoop(engine, tm, poll_interval=0.1)

            loop.start()
            assert loop._loop_thread is not None

            loop.stop()
            assert not loop._loop_thread.is_alive()

    def test_enable_disable(self):
        """Test enabling/disabling autonomy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None)
            loop = AutonomousLoop(engine, tm)

            assert not loop.is_enabled()
            loop.enable()
            assert loop.is_enabled()
            loop.disable()
            assert not loop.is_enabled()

    def test_rate_limiting(self):
        """Test rate limiting prevents spam."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None, confidence_threshold=0.0)
            loop = AutonomousLoop(engine, tm, max_tasks_per_hour=2)

            loop.start()

            # Create multiple decisions and force task creation
            decision1 = AutonomousDecision(
                should_act=True,
                reason="test1",
                confidence=1.0,
                proposed_task={"goal": "auto1", "priority": 5, "mode": "background"}
            )
            decision2 = AutonomousDecision(
                should_act=True,
                reason="test2",
                confidence=1.0,
                proposed_task={"goal": "auto2", "priority": 5, "mode": "background"}
            )

            loop._maybe_create_task(decision1)
            loop._maybe_create_task(decision2)

            created = loop.get_created_tasks()
            loop.stop()

            # Only 2 should be created due to limit
            assert len(created) <= 2

    def test_duplicate_detection(self):
        """Test deduplication prevents spam."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None)
            loop = AutonomousLoop(engine, tm, max_tasks_per_hour=100)

            # Create a task
            tm.create_task("check logs", mode="background")

            # Try to create same task
            proposed = {"goal": "check logs", "priority": 5, "mode": "background"}
            is_dup = loop._is_duplicate_task(proposed)

            assert is_dup

    def test_goal_similarity(self):
        """Test string similarity matching."""
        sim = AutonomousLoop._goal_similarity("check system", "check system health")
        assert sim > 0.5

        sim2 = AutonomousLoop._goal_similarity("abc", "xyz")
        assert sim2 == 0.0

    def test_decision_callback(self):
        """Test decision callback is called."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None)
            loop = AutonomousLoop(engine, tm, poll_interval=0.1)

            callback_called = []

            def callback(decision):
                callback_called.append(decision)

            loop.set_decision_callback(callback)
            loop.start()

            import time
            time.sleep(0.3)

            loop.stop()

            assert len(callback_called) > 0

    def test_recent_decisions_history(self):
        """Test decision history is maintained."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            tm = TaskManager(storage_path=path)
            bus = EventBus()
            agg = ContextAggregator(tm, bus)
            engine = DecisionEngine(agg, tm, llm=None)
            loop = AutonomousLoop(engine, tm, poll_interval=0.1)

            loop.start()

            import time
            time.sleep(0.3)

            decisions = loop.get_recent_decisions(limit=5)
            loop.stop()

            assert len(decisions) > 0
            assert all("should_act" in d for d in decisions)
