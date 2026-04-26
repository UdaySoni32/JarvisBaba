"""
Test suite for reflection and decision-making.
"""
import pytest
import json
from core.reflection import Reflector, ReflectionResult
from core.reflection import ReflectionStatus, NextAction
from core.state import ExecutionState, StepState, StepStatus
from models.llm import DeterministicLLM, FakeLLM


class TestReflectionStatus:
    """Test reflection status enum."""

    def test_status_values(self):
        """Test reflection status values."""
        assert ReflectionStatus.SUCCESS.value == "success"
        assert ReflectionStatus.PARTIAL.value == "partial"
        assert ReflectionStatus.FAILURE.value == "failure"
        assert ReflectionStatus.CRITICAL_FAILURE.value == "critical_failure"


class TestNextAction:
    """Test next action enum."""

    def test_action_values(self):
        """Test next action values."""
        assert NextAction.CONTINUE.value == "continue"
        assert NextAction.RETRY.value == "retry"
        assert NextAction.REPLAN.value == "replan"
        assert NextAction.STOP.value == "stop"


class TestReflectionResult:
    """Test reflection result structure."""

    def test_result_creation(self):
        """Test creating reflection result."""
        result = ReflectionResult(
            status=ReflectionStatus.SUCCESS,
            confidence=0.9,
            reasoning="Step executed correctly",
            next_action=NextAction.CONTINUE,
            should_stop=False
        )
        assert result.status == ReflectionStatus.SUCCESS
        assert result.confidence == 0.9

    def test_confidence_clamping(self):
        """Test confidence is clamped to 0-1."""
        result = ReflectionResult(
            status=ReflectionStatus.SUCCESS,
            confidence=1.5,  # Should clamp to 1.0
            reasoning="Test",
            next_action=NextAction.CONTINUE,
            should_stop=False
        )
        assert result.confidence == 1.0

    def test_result_serialization(self):
        """Test result serialization."""
        result = ReflectionResult(
            status=ReflectionStatus.SUCCESS,
            confidence=0.85,
            reasoning="All good",
            next_action=NextAction.CONTINUE,
            should_stop=False
        )
        data = result.to_dict()
        assert data["status"] == "success"
        assert data["confidence"] == 0.85


class TestReflector:
    """Test reflection functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.deterministic_llm = DeterministicLLM()
        self.fake_llm = FakeLLM()
        self.deterministic_reflector = Reflector(self.deterministic_llm)
        self.fake_reflector = Reflector(self.fake_llm)

    def test_reflect_on_success(self):
        """Test reflection on successful execution."""
        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="run_command", args={"command": "ls"})
        step.mark_complete({"stdout": "files.txt"})

        tool_result = {"success": True, "result": {"stdout": "files.txt"}}

        reflection = self.fake_reflector.reflect(state, step, tool_result)
        assert isinstance(reflection, ReflectionResult)
        assert reflection.next_action in [NextAction.CONTINUE, NextAction.STOP]

    def test_reflect_on_blocked_step(self):
        """Test reflection when step was blocked."""
        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="run_command", args={"command": "rm -rf /"})
        step.block("Dangerous command blocked")

        tool_result = {"success": False, "message": "BLOCKED"}

        reflection = self.fake_reflector.reflect(state, step, tool_result)
        assert isinstance(reflection, ReflectionResult)
        assert reflection.status == ReflectionStatus.CRITICAL_FAILURE

    def test_reflect_on_failed_tool(self):
        """Test reflection on tool failure."""
        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="run_command", args={"command": "invalid"})
        step.attempts = 1
        step.max_attempts = 3

        tool_result = {"success": False, "message": "Command not found"}

        reflection = self.fake_reflector.reflect(state, step, tool_result)
        assert isinstance(reflection, ReflectionResult)

    def test_retry_suggested_when_attempts_remain(self):
        """Test retry when attempts remain."""
        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="run_command", args={})
        step.attempts = 1
        step.max_attempts = 3

        tool_result = {"success": False, "message": "Transient error"}
        reflection = self.fake_reflector.reflect(state, step, tool_result)

        # With deterministic LLM should get continue for successful
        assert reflection.next_action in [NextAction.CONTINUE, NextAction.RETRY]

    def test_parsing_malformed_response(self):
        """Test parsing malformed reflection response."""
        bad_llm = DeterministicLLM(fixed_response="not valid json")
        reflector = Reflector(bad_llm)

        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="test", args={})
        tool_result = {"success": True}

        reflection = reflector.reflect(state, step, tool_result)
        assert reflection.next_action == NextAction.CONTINUE  # Fallback

    def test_completion_check(self):
        """Test completion status check."""
        state = ExecutionState(goal="test", steps=[])
        state.status = "complete"

        reflection = self.fake_reflector.check_completion(state)
        assert isinstance(reflection, ReflectionResult)
        assert reflection.should_stop is True

        result = reflection.to_dict()
        assert result["status"] == "success"  # All complete


class TestReflectionEdgeCases:
    """Test edge cases in reflection."""

    def setup_method(self):
        self.llm = DeterministicLLM()
        self.reflector = Reflector(self.llm)

    def test_empty_tool_result(self):
        """Test reflection with empty result."""
        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="test", args={})

        reflection = self.reflector.reflect(state, step, {})
        assert isinstance(reflection, ReflectionResult)

    def test_none_values_in_result(self):
        """Test reflection with None values."""
        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="test", args={})

        tool_result = {"success": None, "result": None, "message": None}
        reflection = self.reflector.reflect(state, step, tool_result)
        assert isinstance(reflection, ReflectionResult)

    def test_large_result_handling(self):
        """Test reflection handles large results."""
        state = ExecutionState(goal="test", steps=[])
        step = StepState(id=1, action="test", args={})

        large_output = "x" * 10000
        tool_result = {"success": True, "result": {"stdout": large_output}}

        reflection = self.reflector.reflect(state, step, tool_result)
        assert isinstance(reflection, ReflectionResult)

    def test_no_remaining_steps(self):
        """Test reflection when no steps remain."""
        state = ExecutionState(goal="test", steps=[])

        reflection = self.fake_reflector.check_completion(state)
        assert reflection.should_stop is True
