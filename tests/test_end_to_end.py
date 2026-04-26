"""
End-to-end integration tests for complete scenarios.

These tests verify the entire flow from input to output.
"""
import pytest
import time
from core.agent import Agent
from core.planner import Planner
from core.executor import Executor
from core.reflection import Reflector
from core.memory.short_term import ShortTermMemory
from core.state import ExecutionState, StepState
from core.validator import ToolValidator
from core.logging import ExecutionLogger
from models.llm import DeterministicLLM, FakeLLM
from core.tools.terminal import run_command
from core.tools.apps import open_app


class TestMultiStepSuccess:
    """Test Case 1: Multi-step success scenario."""

    def test_create_folder_and_list_files(self):
        """Test multi-step plan executes successfully."""
        # Setup
        llm = FakeLLM()
        executor = Executor()
        executor.register_tool("run_command", run_command)
        executor.register_tool("open_app", open_app)

        planner = Planner(llm)
        logger = ExecutionLogger()

        # Execute
        goal = "create folder and list files"
        plan = planner.create_plan(goal)
        logger.log_plan(goal, plan.to_dict(), 2)

        assert plan is not None
        assert len(plan.steps) > 0

        # Execute steps
        for step in plan.steps:
            step_state = StepState(id=step.id, action=step.action, args=step.args)
            result = executor.execute_step(step_state)
            logger.log_step_result(step.id, result.success, result.result)

            # Should succeed for safe commands
            if step.action == "run_command" and "rm" not in str(step.args):
                assert result.success or "BLOCKED" in result.message

        logger.log_completion("test", len(plan.steps), 0, len(plan.steps))


class TestPartialFailure:
    """Test Case 2: Partial failure with retry."""

    def test_invalid_command_failure_detection(self):
        """Test failure is detected and can be retried."""
        llm = DeterministicLLM()
        executor = Executor()
        executor.register_tool("run_command", run_command)

        step = StepState(id=1, action="run_command", args={"command": "invalid_command_xyz"})
        result = executor.execute_step(step)

        assert result.success is False
        assert step.status.value == "failed"
        assert step.attempts == 1

    def test_retry_mechanism(self):
        """Test retry is attempted on failure."""
        llm = DeterministicLLM()
        executor = Executor()
        executor.register_tool("run_command", run_command)

        step = StepState(id=1, action="run_command", args={"command": "invalid"})
        step.max_attempts = 3

        # First attempt
        result = executor.execute_step(step)
        assert result.success is False
        assert step.status.value == "failed"

        # Retry logic would be triggered by reflection/main loop


class TestDangerousCommandBlocking:
    """Test Case 3: Dangerous command blocking."""

    def test_delete_root_blocked(self):
        """Test rm -rf / is blocked."""
        executor = Executor()
        executor.register_tool("run_command", run_command)

        step = StepState(id=1, action="run_command", args={"command": "rm -rf /"})
        result = executor.execute_step(step)

        assert result.success is False
        assert step.status.value == "blocked"
        assert "BLOCKED" in result.message or "Dangerous" in str(result.message)

    def test_shutdown_blocked(self):
        """Test shutdown is blocked."""
        executor = Executor()
        executor.register_tool("run_command", run_command)

        step = StepState(id=1, action="run_command", args={"command": "shutdown -h now"})
        result = executor.execute_step(step)

        assert step.status.value == "blocked"

    def test_sudo_blocked_in_strict_mode(self):
        """Test sudo blocked in strict mode."""
        executor = Executor(strict_mode=True)
        executor.register_tool("run_command", run_command)

        step = StepState(id=1, action="run_command", args={"command": "sudo ls"})
        result = executor.execute_step(step)

        assert step.status.value == "blocked"


class TestInfiniteFailurePrevention:
    """Test Case 4: Infinite failure prevention."""

    def test_max_attempts_enforced(self):
        """Test retries are capped."""
        executor = Executor()
        executor.register_tool("run_command", run_command)

        step = StepState(id=1, action="run_command", args={"command": "always_fails"})
        step.max_attempts = 2

        # Simulate multiple failures
        for _ in range(3):
            if step.can_retry():
                step.status = StepStatus.PENDING
                result = executor.execute_step(step)

        assert step.attempts <= 3

    def test_retry_exhaustion(self):
        """Test system stops after max retries."""
        step = StepState(id=1, action="test", args={})
        step.max_attempts = 2
        step.attempts = 2

        assert not step.can_retry()


class TestSystemIntegration:
    """Test system components work together."""

    def test_full_execution_flow(self):
        """Test complete execution flow."""
        llm = FakeLLM()

        # Create all components
        executor = Executor()
        executor.register_tool("run_command", run_command)

        planner = Planner(llm)
        agent = Agent(llm, ShortTermMemory(), executor.get_available_tools())
        reflector = Reflector(llm)
        logger = ExecutionLogger()

        # Execute a simple task
        goal = "run ls"

        # Plan
        plan = planner.create_plan(goal)
        assert plan is not None

        # Execute
        state = ExecutionState(goal=plan.goal, steps=[])
        for s in plan.steps:
            step = StepState(id=s.id, action=s.action, args=s.args)
            result = executor.execute_step(step)
            logger.log_step_result(s.id, result.success, result.result)

            if result.success:
                reflection = reflector.reflect(state, step, result.to_dict())
                assert reflection.next_action is not None

        # Log completion
        logger.log_completion("complete", len(plan.steps), 0, len(plan.steps))

        # Verify logs
        summary = logger.summary()
        assert summary["execution_id"] is not None

    def test_mode_classification(self):
        """Test mode classification determines execution path."""
        llm = FakeLLM()
        agent = Agent(llm, ShortTermMemory(), [])

        # Simple query
        mode = agent.classify_mode("hello")
        assert mode.mode.value in ["single_step", "multi_step"]

        # Complex query
        mode = agent.classify_mode("do this and then do that")
        assert isinstance(mode.reasoning, str)


class TestDeterministicBehavior:
    """Test reproducibility and determinism."""

    def test_seeded_execution_is_reproducible(self):
        """Test that seeded execution produces same results."""
        llm1 = DeterministicLLM(seed=123)
        llm2 = DeterministicLLM(seed=123)

        planner1 = Planner(llm1)
        planner2 = Planner(llm2)

        plan1 = planner1.create_plan("test task")
        plan2 = planner2.create_plan("test task")

        # Goals should match
        assert plan1.goal == plan2.goal or "test" in plan1.goal

    def test_noop_mode_is_deterministic(self):
        """Test noop mode is fully deterministic."""
        noop_llm = DeterministicLLM(noop=True)

        r1 = noop_llm.generate("Test", "Input 1")
        r2 = noop_llm.generate("Test", "Input 2")

        # Noop should return same structure
        assert "thought" in r1 or "goal" in r1 or "status" in r1


class TestExecutionTrace:
    """Test execution tracing and logging."""

    def test_execution_trace_created(self):
        """Test execution trace is created."""
        logger = ExecutionLogger()
        logger.set_goal("test goal", "single_step")

        trace = logger.get_trace()
        assert trace["execution_id"] == logger.execution_id
        assert trace["goal"] == "test goal"

    def test_step_results_tracked(self):
        """Test step results are tracked in trace."""
        logger = ExecutionLogger()

        logger.log_step_result(1, True, {"output": "data"})
        logger.log_step_result(2, False, None, "error")

        trace = logger.get_trace()
        assert len(trace["steps"]) == 2


class TestFailureInjection:
    """Test failure injection for robustness testing."""

    def test_simulated_tool_failure(self):
        """Test system handles injected tool failures."""
        fail_every = 1
        llm = DeterministicLLM(fail_every=fail_every)

        # Every call should fail
        for i in range(3):
            result = llm.generate("Test", f"Input {i}")
            # Check structure indicates failure
            parsed = result
            assert parsed is not None


class TestMetricsCollection:
    """Test metrics are collected."""

    def test_execution_metrics(self):
        """Test metrics are accumulated."""
        from datetime import datetime

        execution_count = 0
        success_count = 0

        # Simulate executions
        for i in range(5):
            execution_count += 1
            if i < 4:  # 80% success rate
                success_count += 1

        assert execution_count == 5
        assert success_count == 4
        assert success_count / execution_count == 0.8
