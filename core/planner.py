"""
Planner module - Generates multi-step plans for complex tasks.

The Planner takes a user goal and available tools, then generates
a structured plan of sequential steps to accomplish that goal.
"""
import json
from typing import List, Dict, Any, Optional
from models.llm import LLMInterface
from core.tools.schema import get_tool_schemas, get_tool_schemas_text


class PlanStep:
    """A single step in an execution plan."""

    def __init__(self, step_id: int, action: str, args: Dict[str, Any]):
        self.id = step_id
        self.action = action
        self.args = args
        self.result: Optional[Any] = None
        self.status: str = "pending"  # pending, running, success, failed
        self.reflection: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "args": self.args,
            "result": self.result,
            "status": self.status,
            "reflection": self.reflection
        }

    def mark_running(self):
        self.status = "running"

    def mark_complete(self, result: Any):
        self.status = "success"
        self.result = result

    def mark_failed(self, error: str):
        self.status = "failed"
        self.result = {"error": error}

    @property
    def is_complete(self) -> bool:
        return self.status in ("success", "failed")


class Plan:
    """A complete multi-step plan for a goal."""

    def __init__(self, goal: str, steps: List[PlanStep]):
        self.goal = goal
        self.steps = steps
        self.current_step_index: int = 0
        self.status: str = "pending"  # pending, running, complete, failed

    @property
    def current_step(self) -> Optional[PlanStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def is_complete(self) -> bool:
        return self.status in ("complete", "failed") or \
               self.current_step_index >= len(self.steps)

    @property
    def completed_steps(self) -> List[PlanStep]:
        return [s for s in self.steps if s.is_complete]

    @property
    def remaining_steps(self) -> List[PlanStep]:
        return [s for s in self.steps if not s.is_complete]

    def advance(self) -> bool:
        """Move to next step. Returns False if no more steps."""
        self.current_step_index += 1
        if self.current_step_index >= len(self.steps):
            self.status = "complete"
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "current_step": self.current_step_index,
            "steps": [s.to_dict() for s in self.steps]
        }


class Planner:
    """
    The Planner generates structured multi-step plans using an LLM.
    It understands available tools and creates executable step sequences.
    """

    def __init__(self, llm: LLMInterface):
        self.llm = llm
        self.tool_schemas = get_tool_schemas()

    def _build_system_prompt(self) -> str:
        """Build the system prompt for planning."""
        tools_text = get_tool_schemas_text()

        return f"""You are a Task Planner AI. Your job is to break down user goals into specific, actionable steps.

Available tools:
{tools_text}

You MUST respond with valid JSON in this exact format:
{{
    "goal": "Restated clear goal",
    "steps": [
        {{
            "id": 1,
            "action": "tool_name",
            "args": {{"param": "value"}}
        }}
    ]
}}

Planning rules:
1. Generate 1-6 steps maximum
2. Each step must use exactly ONE tool
3. Steps must be sequential and logical
4. Use previous step outputs to inform next steps when needed
5. If a task is simple (1 step), still use the same format
6. Always validate arguments match the tool's parameter schema

If the goal cannot be achieved with available tools, return an empty steps list and explain in the goal field.
"""

    def _build_user_prompt(self, goal: str) -> str:
        """Build the user prompt with the goal."""
        return f"""Create a plan to accomplish this goal:

"{goal}"

Analyze the task, break it into logical steps, and output the JSON plan.
Each step should use one of the available tools."""

    def create_plan(self, goal: str) -> Plan:
        """
        Generate a multi-step plan for the given goal.

        Args:
            goal: The user's high-level objective

        Returns:
            Plan object with structured steps
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(goal)

        try:
            raw_response = self.llm.generate(system_prompt, user_prompt)

            # Parse JSON response
            plan_data = self._parse_response(raw_response)

            # Convert to PlanStep objects
            steps = []
            for step_data in plan_data.get("steps", []):
                step = PlanStep(
                    step_id=step_data.get("id", len(steps) + 1),
                    action=step_data.get("action"),
                    args=step_data.get("args", {})
                )
                steps.append(step)

            plan = Plan(goal=plan_data.get("goal", goal), steps=steps)
            return plan

        except Exception as e:
            # Return empty plan on failure
            return Plan(
                goal=goal,
                steps=[],
                status="failed"
            )

    def _parse_response(self, raw_response: str) -> Dict[str, Any]:
        """Parse LLM response into plan data."""
        import re

        # Try direct JSON parse
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks
        json_match = re.search(
            r'```(?:json)?\s*(\{.*?\})\s*```',
            raw_response,
            re.DOTALL
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Fallback: try to find any JSON-like structure
        match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Ultimate fallback
        return {
            "goal": "Failed to parse plan",
            "steps": []
        }

    def replan(self, plan: Plan, failure_reason: str) -> Plan:
        """
        Generate a revised plan based on execution failure.

        Args:
            plan: The current failed or partial plan
            failure_reason: Description of what went wrong

        Returns:
            New Plan object with adjusted steps
        """
        context = json.dumps(plan.to_dict(), indent=2)

        system_prompt = f"""You are a Task Planner AI. A previous plan failed and needs revision.

Available tools:
{get_tool_schemas_text()}

You MUST respond with valid JSON in this exact format:
{{
    "goal": "Restated clear goal",
    "steps": [
        {{
            "id": 1,
            "action": "tool_name",
            "args": {{"param": "value"}}
        }}
    ]
}}

Consider what went wrong and create a better plan."""

        user_prompt = f"""The following plan failed:

Failure reason: {failure_reason}

Previous plan:
{context}

Create a revised plan to accomplish the goal."""

        try:
            raw_response = self.llm.generate(system_prompt, user_prompt)
            plan_data = self._parse_response(raw_response)

            steps = []
            for step_data in plan_data.get("steps", []):
                step = PlanStep(
                    step_id=step_data.get("id", len(steps) + 1),
                    action=step_data.get("action"),
                    args=step_data.get("args", {})
                )
                steps.append(step)

            return Plan(goal=plan_data.get("goal", plan.goal), steps=steps)

        except Exception as e:
            return Plan(
                goal=plan.goal,
                steps=[],
                status="failed"
            )
