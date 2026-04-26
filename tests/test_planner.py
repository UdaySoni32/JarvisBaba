"""
Test suite for plan generation.
"""
import pytest
import json
from core.planner import Planner, Plan, PlanStep
from models.llm import DeterministicLLM, FakeLLM


class TestPlanner:
    """Test multi-step planning functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.deterministic_llm = DeterministicLLM(fixed_plan=True)
        self.fake_llm = FakeLLM()
        self.deterministic_planner = Planner(self.deterministic_llm)
        self.fake_planner = Planner(self.fake_llm)

    def test_create_simple_plan(self):
        """Test creating a simple single-step plan."""
        plan = self.deterministic_planner.create_plan("simple task")
        assert isinstance(plan, Plan)
        assert plan.goal is not None
        assert len(plan.steps) >= 0

    def test_create_multi_step_plan(self):
        """Test creating a multi-step plan."""
        plan = self.fake_planner.create_plan("open firefox and then run pwd")
        assert isinstance(plan, Plan)
        assert len(plan.steps) > 0
        assert all(isinstance(s, PlanStep) for s in plan.steps)

    def test_plan_has_valid_steps(self):
        """Test that plan steps have valid structure."""
        plan = self.fake_planner.create_plan("run ls and then run pwd")
        for step in plan.steps:
            assert step.id > 0
            assert step.action in ["run_command", "open_app"]
            assert isinstance(step.args, dict)

    def test_plan_step_ids_are_sequential(self):
        """Test that step IDs are sequential."""
        plan = self.fake_planner.create_plan("multiple actions")
        ids = [s.id for s in plan.steps]
        assert ids == sorted(ids)

    def test_plan_to_dict(self):
        """Test plan serialization."""
        plan = self.fake_planner.create_plan("test task")
        data = plan.to_dict()
        assert "goal" in data
        assert "steps" in data
        assert isinstance(data["steps"], list)

    def test_plan_step_states(self):
        """Test plan step state management."""
        plan = self.fake_planner.create_plan("test")
        for step in plan.steps:
            assert step.status == "pending"
            step.mark_running()
            assert step.status == "running"
            step.mark_complete("result")
            assert step.status == "success"
            assert step.result == "result"

    def test_plan_step_is_complete(self):
        """Test step completion detection."""
        plan = self.fake_planner.create_plan("test")
        if plan.steps:
            step = plan.steps[0]
            assert not step.is_complete
            step.mark_failed("error")
            assert step.is_complete

    def test_plan_current_step(self):
        """Test plan current step tracking."""
        plan = self.fake_planner.create_plan("multi step task")
        if len(plan.steps) >= 2:
            assert plan.current_step == plan.steps[0]
            plan.advance()
            assert plan.current_step == plan.steps[1]

    def test_plan_advance(self):
        """Test plan advancement."""
        plan = self.fake_planner.create_plan("test")
        if plan.steps:
            assert plan.current_step_index == 0
            has_more = plan.advance()
            if len(plan.steps) > 1:
                assert has_more is True
                assert plan.current_step_index == 1
            else:
                assert has_more is False

    def test_plan_is_complete(self):
        """Test plan completion detection."""
        plan = self.fake_planner.create_plan("simple task")
        # Initially not complete
        assert not plan.is_complete

        # Complete all steps
        for step in plan.steps:
            step.mark_complete("done")

        if plan.steps:
            assert plan.is_complete

    def test_replan_on_failure(self):
        """Test replanning after failure."""
        original = self.fake_planner.create_plan("original task")
        revised = self.fake_planner.replan(original, "First approach failed")
        assert isinstance(revised, Plan)
        assert revised.goal is not None

    def test_parser_handles_malformed_json(self):
        """Test parser handles malformed JSON gracefully."""
        # Create LLM that returns bad JSON
        bad_llm = DeterministicLLM(fixed_response="not json")
        planner = Planner(bad_llm)
        plan = planner.create_plan("test")
        assert isinstance(plan, Plan)

    def test_parser_extracts_json_from_markdown(self):
        """Test parser extracts JSON from markdown blocks."""
        markdown_json = '```json\n{"goal": "test", "steps": []}\n```'
        bad_llm = DeterministicLLM(fixed_response=markdown_json)
        planner = Planner(bad_llm)
        plan = planner.create_plan("test")
        assert plan.goal == "test"


class TestDeterministicPlanning:
    """Test with deterministic LLM for reproducibility."""

    def test_seeded_plan_generation(self):
        """Test that seeded generation is reproducible."""
        llm1 = DeterministicLLM(seed=42)
        llm2 = DeterministicLLM(seed=42)

        planner1 = Planner(llm1)
        planner2 = Planner(llm2)

        plan1 = planner1.create_plan("test task")
        plan2 = planner2.create_plan("test task")

        assert len(plan1.steps) == len(plan2.steps)

    def test_noop_mode(self):
        """Test noop mode returns minimal valid responses."""
        noop_llm = DeterministicLLM(noop=True)
        planner = Planner(noop_llm)
        plan = planner.create_plan("test")
        assert isinstance(plan.goal, str)
