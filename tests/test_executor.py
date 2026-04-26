"""
Test suite for tool execution.
"""
import pytest
from unittest.mock import Mock, MagicMock
from core.executor import Executor, ExecutionResult
from core.state import StepState
from core.agent import AgentDecision


class MockTool:
    """Mock tool for testing."""

    def __init__(self, return_value=None, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect
        self.call_count = 0
        self.last_args = None

    def __call__(self, **kwargs):
        self.call_count += 1
        self.last_args = kwargs
        if self.side_effect:
            raise self.side_effect
        return self.return_value


class FailingTool:
    """Tool that always fails."""

    def __call__(self, **kwargs):
        raise RuntimeError("Tool failure")


class TestExecutor:
    """Test tool execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = Executor()
        self.mock_tool = MockTool(return_value={"stdout": "output", "stderr": ""})
        self.executor.register_tool("mock_tool", self.mock_tool)

    def test_register_tool(self):
        """Test tool registration."""
        executor = Executor()
        test_tool = MockTool()
        executor.register_tool("test_tool", test_tool)
        assert executor.has_tool("test_tool")

    def test_execute_agent_decision(self):
        """Test executing agent decision."""
        decision = AgentDecision(
            thought="Test",
            action="mock_tool",
            args={"param": "value"},
            response=None
        )
        result = self.executor.execute(decision)
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert self.mock_tool.call_count == 1

    def test_execute_step_state(self):
        """Test executing step state."""
        step = StepState(
            id=1,
            action="mock_tool",
            args={"param": "value"}
        )
        result = self.executor.execute_step(step)
        assert result.success is True
        assert step.status.value == "success"
        assert step.result == self.mock_tool.return_value

    def test_validate_before_execution(self):
        """Test validation runs before execution."""
        # Dangerous command should be blocked
        self.executor.register_tool("run_command", lambda **x: x)
        step = StepState(
            id=1,
            action="run_command",
            args={"command": "rm -rf /"}
        )
        result = self.executor.execute_step(step)
        assert result.success is False
        assert step.status.value == "blocked"

    def test_step_attempts_tracking(self):
        """Test that step attempts are tracked."""
        step = StepState(
            id=1,
            action="mock_tool",
            args={}
        )
        assert step.attempts == 0
        self.executor.execute_step(step)
        assert step.attempts == 1

    def test_unknown_tool_rejection(self):
        """Test that unknown tools are rejected."""
        decision = AgentDecision(
            thought="Test",
            action="unknown_tool",
            args={},
            response=None
        )
        result = self.executor.execute(decision)
        assert result.success is False
        assert "Unknown tool" in result.message

    def test_no_action_returns_noop(self):
        """Test that no action returns noop result."""
        decision = AgentDecision(
            thought="Direct response",
            action=None,
            args={},
            response="Hello"
        )
        result = self.executor.execute(decision)
        assert result.success is True
        assert result.action is None

    def test_tool_exception_handling(self):
        """Test exception handling in tool execution."""
        executor = Executor()
        executor.register_tool("failing_tool", FailingTool())

        step = StepState(
            id=1,
            action="failing_tool",
            args={}
        )
        result = executor.execute_step(step)
        assert result.success is False
        assert "Error executing" in result.message
        assert step.status.value == "failed"

    def test_step_failure_marking(self):
        """Test that failed steps are properly marked."""
        executor = Executor()
        executor.register_tool("fail", FailingTool())

        step = StepState(id=1, action="fail", args={})
        executor.execute_step(step)

        assert step.status.value == "failed"
        assert step.error is not None


class TestExecutionResult:
    """Test ExecutionResult data structure."""

    def test_result_creation(self):
        """Test result creation."""
        result = ExecutionResult(
            success=True,
            action="test",
            result={"data": "value"},
            message="Success"
        )
        assert result.success is True
        assert result.action == "test"

    def test_result_to_dict(self):
        """Test result serialization."""
        result = ExecutionResult(
            success=True,
            action="test",
            result={"data": "value"},
            message="OK"
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["message"] == "OK"


class TestExecutorIntegration:
    """Integration tests for executor with other components."""

    def test_executor_with_validation_blocked(self):
        """Test executor blocks dangerous commands."""
        from core.executor import Executor

        executor = Executor()
        executor.register_tool("run_command", lambda **x: x)

        step = StepState(
            id=1,
            action="run_command",
            args={"command": "shutdown -h now"}
        )
        result = executor.execute_step(step)

        assert result.success is False
        assert step.status.value == "blocked"

    def test_executor_validates_multiple_steps(self):
        """Test batch validation."""
        executor = Executor()

        steps = [
            StepState(id=1, action="run_command", args={"command": "ls"}),
            StepState(id=1, action="run_command", args={"command": "rm -rf /"}),
        ]

        results = []
        for step in steps:
            results.append(executor.execute_step(step))

        assert results[0].success is True  # Valid
        assert results[1].success is False  # Blocked
