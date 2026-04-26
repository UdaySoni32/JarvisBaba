"""Phase 4 Functional Validation Tests

Tests for:
- Goal System (create, list, link tasks)
- Async Approval Workflow (non-blocking)
- Alignment Layer (rules, preferences, forbidden actions)
- Enhanced Decision Engine (goal-aware, alignment-aware)
- Learning System (pattern memory, feedback)
- Autonomy Modes (OFF, SUGGEST, ASSIST, FULL)
"""

import json
import os
import tempfile
from datetime import datetime

import pytest

from core.goals.goal import Goal, GOAL_STATUSES
from core.goals.goal_manager import GoalManager
from core.alignment import AlignmentLayer
from core.learning import PatternMemory, FeedbackCollector
from core.tasks.task import Task
from core.tasks.task_manager import TaskManager
from core.decision_engine import DecisionEngine, AutonomousDecision
from core.context_aggregator import ContextAggregator
from core.events import EventBus
from core.agent import Agent
from core.memory.short_term import ShortTermMemory
from models.llm import FakeLLM


class TestGoalSystem:
    """Test goal creation, hierarchy, and persistence."""

    def test_goal_creation(self):
        """Test creating a goal."""
        goal = Goal(
            description="Test goal",
            priority=5,
            success_criteria="Task completed successfully"
        )
        assert goal.description == "Test goal"
        assert goal.priority == 5
        assert goal.status == "active"
        assert len(goal.task_ids) == 0

    def test_goal_hierarchy(self):
        """Test parent-child goal relationships."""
        parent = Goal(description="Parent goal", priority=9)
        child = Goal(description="Child goal", priority=5, parent_goal_id=parent.id)
        
        assert child.parent_goal_id == parent.id
        assert child.priority < parent.priority

    def test_goal_transitions(self):
        """Test goal status transitions."""
        goal = Goal(description="Test")
        
        assert goal.status == "active"
        goal.transition_to("paused")
        assert goal.status == "paused"
        goal.transition_to("active")
        assert goal.status == "active"
        goal.transition_to("completed")
        assert goal.status == "completed"

    def test_goal_persistence(self):
        """Test goal storage and recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "goals.json")
            manager = GoalManager(storage_path=storage)
            
            goal1 = manager.create_goal("Goal 1", priority=9)
            goal2 = manager.create_goal("Goal 2", priority=5, parent_goal_id=goal1.id)
            
            # Recover from disk
            manager2 = GoalManager(storage_path=storage)
            goals = manager2.list_goals()
            
            assert len(goals) == 2
            assert goals[0].id == goal1.id
            assert goals[1].parent_goal_id == goal1.id

    def test_task_goal_linking(self):
        """Test linking tasks to goals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_storage = os.path.join(tmpdir, "goals.json")
            task_storage = os.path.join(tmpdir, "tasks.json")
            
            goal_manager = GoalManager(storage_path=goal_storage)
            task_manager = TaskManager(storage_path=task_storage)
            
            goal = goal_manager.create_goal("Test goal")
            task = task_manager.create_task("Test task", goal_id=goal.id)
            goal_manager.link_task_to_goal(goal.id, task.id)
            
            assert task.goal_id == goal.id
            linked_tasks = goal_manager.get_tasks_for_goal(goal.id)
            assert task.id in linked_tasks


class TestAsyncApprovalWorkflow:
    """Test non-blocking approval system."""

    def test_task_waiting_approval_status(self):
        """Test WAITING_APPROVAL status."""
        task = Task(goal="Test", status="pending")
        
        # Transition to waiting approval
        task.transition_to("waiting_approval")
        assert task.status == "waiting_approval"

    def test_approval_workflow(self):
        """Test approval and rejection flow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "tasks.json")
            manager = TaskManager(storage_path=storage)
            
            task = manager.create_task("Test task", requires_approval=True)
            manager.set_task_approval_needed(task.id, "Testing approval")
            
            assert task.status == "waiting_approval"
            assert task.requires_approval
            
            # Approve
            approved = manager.approve_task(task.id)
            assert approved
            assert task.status == "pending"
            
            # Reject another task
            task2 = manager.create_task("Test task 2", requires_approval=True)
            manager.set_task_approval_needed(task2.id, "Testing rejection")
            rejected = manager.reject_task(task2.id, "Not needed")
            assert rejected
            assert task2.status == "failed"

    def test_pending_approvals_list(self):
        """Test listing tasks waiting for approval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "tasks.json")
            manager = TaskManager(storage_path=storage)
            
            t1 = manager.create_task("Task 1")
            t2 = manager.create_task("Task 2")
            t3 = manager.create_task("Task 3")
            
            manager.set_task_approval_needed(t1.id, "Reason 1")
            manager.set_task_approval_needed(t2.id, "Reason 2")
            
            pending = manager.list_pending_approvals()
            assert len(pending) == 2
            assert all(t.status == "waiting_approval" for t in pending)


class TestAlignmentLayer:
    """Test user preferences and safety rules."""

    def test_hard_rules(self):
        """Test hard rule enforcement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "alignment.json")
            alignment = AlignmentLayer(storage_path=storage)
            
            # Default: installs require approval
            assert alignment.requires_approval("installs")
            assert alignment.requires_approval("system_commands")
            
            # Update rule
            alignment.set_hard_rule("require_approval_for_installs", False)
            assert not alignment.requires_approval("installs")

    def test_forbidden_actions(self):
        """Test forbidden action patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "alignment.json")
            alignment = AlignmentLayer(storage_path=storage)
            
            # Default forbidden patterns
            assert alignment.is_forbidden("rm -rf /")
            assert alignment.is_forbidden("sudo reboot")
            assert not alignment.is_forbidden("echo hello")

    def test_soft_preferences(self):
        """Test soft preference storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "alignment.json")
            alignment = AlignmentLayer(storage_path=storage)
            
            assert alignment.get_preference("prefer_local_models") == True
            assert alignment.get_preference("batch_operations") == True
            
            alignment.set_preference("prefer_local_models", False)
            assert alignment.get_preference("prefer_local_models") == False

    def test_persistence(self):
        """Test alignment config persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "alignment.json")
            
            alignment1 = AlignmentLayer(storage_path=storage)
            alignment1.set_hard_rule("require_approval_for_api_calls", False)
            alignment1.add_forbidden_action("custom_dangerous_pattern")
            
            # Recover from disk
            alignment2 = AlignmentLayer(storage_path=storage)
            assert not alignment2.requires_approval("api_calls")
            assert alignment2.is_forbidden("custom_dangerous_pattern")


class TestLearningSystem:
    """Test pattern memory and feedback collection."""

    def test_pattern_recording(self):
        """Test recording task patterns."""
        pattern_memory = PatternMemory()
        
        pattern_memory.record_outcome("install", "ubuntu", "success")
        pattern_memory.record_outcome("install", "ubuntu", "success")
        pattern_memory.record_outcome("install", "ubuntu", "failure")
        
        confidence = pattern_memory.get_pattern_confidence("install", "ubuntu")
        assert 0.5 < confidence < 1.0

    def test_pattern_retrieval(self):
        """Test querying patterns."""
        pattern_memory = PatternMemory()
        
        for i in range(7):
            pattern_memory.record_outcome("test_task", "context_1", "success")
        for i in range(3):
            pattern_memory.record_outcome("test_task", "context_1", "failure")
        
        confidence = pattern_memory.get_pattern_confidence("test_task", "context_1")
        assert confidence > 0.6

    def test_retry_logic(self):
        """Test should_retry_pattern logic."""
        pattern_memory = PatternMemory()
        
        # Highly successful pattern
        for i in range(9):
            pattern_memory.record_outcome("reliable_task", "ctx1", "success")
        for i in range(1):
            pattern_memory.record_outcome("reliable_task", "ctx1", "failure")
        
        assert pattern_memory.should_retry_pattern("reliable_task", "ctx1")
        
        # Highly failing pattern
        for i in range(9):
            pattern_memory.record_outcome("broken_task", "ctx2", "failure")
        
        assert not pattern_memory.should_retry_pattern("broken_task", "ctx2")

    def test_feedback_collection(self):
        """Test feedback logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pattern_memory = PatternMemory()
            feedback_path = os.path.join(tmpdir, "learning.jsonl")
            collector = FeedbackCollector(pattern_memory, storage_path=feedback_path)
            
            collector.record_feedback(
                task_id="task-1",
                task_type="deploy",
                goal_id="goal-1",
                context="production",
                outcome="success",
                execution_time=45.2,
                reasoning="Deployed successfully to prod"
            )
            
            feedback = collector.get_recent_feedback(limit=1)
            assert len(feedback) == 1
            assert feedback[0]["task_id"] == "task-1"
            assert feedback[0]["outcome"] == "success"


class TestEnhancedDecisionEngine:
    """Test goal-aware and alignment-aware decision making."""

    def test_autonomous_decision_with_goal(self):
        """Test decision includes goal context."""
        decision = AutonomousDecision(
            should_act=True,
            reason="Goal needs support",
            confidence=0.8,
            goal_id="goal-123",
            requires_approval=False,
            alignment_score=0.9
        )
        
        assert decision.goal_id == "goal-123"
        assert decision.alignment_score == 0.9
        
        d = decision.to_dict()
        assert d["goal_id"] == "goal-123"
        assert d["alignment_score"] == 0.9

    def test_decision_with_approval(self):
        """Test decision flagging for approval."""
        decision = AutonomousDecision(
            should_act=True,
            reason="Needs user approval",
            confidence=0.7,
            requires_approval=True,
            alignment_score=0.5
        )
        
        assert decision.requires_approval
        assert not decision.goal_id


class TestAutonomyModes:
    """Test autonomy mode system."""

    def test_autonomy_mode_setting(self):
        """Test setting and getting autonomy modes."""
        llm = FakeLLM()
        memory = ShortTermMemory()
        agent = Agent(llm, memory)
        
        # Initial state
        assert agent.get_autonomy_mode() == "off"
        assert not agent.is_autonomy_enabled()
        
        # Set modes
        assert agent.set_autonomy_mode("suggest")
        assert agent.get_autonomy_mode() == "suggest"
        assert agent.is_autonomy_enabled()
        
        assert agent.set_autonomy_mode("assist")
        assert agent.get_autonomy_mode() == "assist"
        
        assert agent.set_autonomy_mode("full")
        assert agent.get_autonomy_mode() == "full"
        
        assert agent.set_autonomy_mode("off")
        assert agent.get_autonomy_mode() == "off"
        assert not agent.is_autonomy_enabled()

    def test_invalid_mode(self):
        """Test invalid mode rejection."""
        llm = FakeLLM()
        memory = ShortTermMemory()
        agent = Agent(llm, memory)
        
        assert not agent.set_autonomy_mode("invalid")
        assert agent.get_autonomy_mode() == "off"

    def test_compatibility_methods(self):
        """Test backward compatibility."""
        llm = FakeLLM()
        memory = ShortTermMemory()
        agent = Agent(llm, memory)
        
        agent.enable_autonomy()
        assert agent.get_autonomy_mode() == "full"
        assert agent.is_autonomy_enabled()
        
        agent.disable_autonomy()
        assert agent.get_autonomy_mode() == "off"
        assert not agent.is_autonomy_enabled()


class TestConcurrency:
    """Test thread safety of new components."""

    def test_goal_manager_thread_safety(self):
        """Test GoalManager under concurrent access."""
        import threading
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "goals.json")
            manager = GoalManager(storage_path=storage)
            
            results = []
            
            def create_goals(count):
                for i in range(count):
                    goal = manager.create_goal(f"Goal {i}")
                    results.append(goal.id)
            
            threads = [threading.Thread(target=create_goals, args=(5,)) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            goals = manager.list_goals()
            assert len(goals) == 15
            assert len(results) == 15

    def test_task_approval_thread_safety(self):
        """Test approval workflow under concurrent access."""
        import threading
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(tmpdir, "tasks.json")
            manager = TaskManager(storage_path=storage)
            
            # Create tasks
            task_ids = []
            for i in range(5):
                task = manager.create_task(f"Task {i}")
                manager.set_task_approval_needed(task.id, f"Reason {i}")
                task_ids.append(task.id)
            
            def approve_tasks(ids):
                for tid in ids:
                    manager.approve_task(tid)
            
            threads = [threading.Thread(target=approve_tasks, args=(task_ids,)) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # All should be approved
            pending = manager.list_pending_approvals()
            assert len(pending) == 0


class TestStateRecovery:
    """Test persistence and recovery after restart."""

    def test_goal_recovery(self):
        """Test goals survive restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_file = os.path.join(tmpdir, "goals.json")
            
            # Create and save
            m1 = GoalManager(storage_path=goal_file)
            g1 = m1.create_goal("Important goal", priority=9)
            g1_id = g1.id
            del m1
            
            # Recover
            m2 = GoalManager(storage_path=goal_file)
            goals = m2.list_goals()
            assert len(goals) == 1
            assert goals[0].id == g1_id

    def test_task_approval_recovery(self):
        """Test approval state survives restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = os.path.join(tmpdir, "tasks.json")
            
            # Create task in waiting approval
            m1 = TaskManager(storage_path=task_file)
            t1 = m1.create_task("Test", requires_approval=True)
            m1.set_task_approval_needed(t1.id, "Reason")
            t1_id = t1.id
            del m1
            
            # Recover
            m2 = TaskManager(storage_path=task_file)
            task = m2.get_task(t1_id)
            assert task.status == "waiting_approval"
            assert task.requires_approval
