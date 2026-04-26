"""
Reflection module - Evaluates step results with detailed classification.

After each step execution, evaluates success/failure and decides next action.
Improved classification with confidence scores.
"""
import json
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
from models.llm import LLMInterface
from core.state import ExecutionState, StepState


class ReflectionStatus(Enum):
    """Detailed status classification."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    CRITICAL_FAILURE = "critical_failure"


class NextAction(Enum):
    """Possible next actions after reflection."""
    CONTINUE = "continue"
    RETRY = "retry"
    REPLAN = "replan"
    STOP = "stop"


@dataclass
class ReflectionResult:
    """Enhanced reflection result."""
    status: ReflectionStatus
    confidence: float  # 0.0 to 1.0
    reasoning: str
    next_action: NextAction
    should_stop: bool
    recovery_suggestion: Optional[str] = None

    def __init__(
        self,
        status: ReflectionStatus,
        confidence: float,
        reasoning: str,
        next_action: NextAction,
        should_stop: bool = False,
        recovery_suggestion: Optional[str] = None
    ):
        self.status = status
        self.confidence = max(0.0, min(1.0, confidence))
        self.reasoning = reasoning
        self.next_action = next_action
        self.should_stop = should_stop
        self.recovery_suggestion = recovery_suggestion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "next_action": self.next_action.value,
            "should_stop": self.should_stop,
            "recovery_suggestion": self.recovery_suggestion
        }


class Reflector:
    """
    The Reflector evaluates execution results and makes structured decisions.
    Uses detailed classification with confidence scoring.
    """

    def __init__(self, llm: LLMInterface):
        self.llm = llm

    def reflect(
        self,
        state: ExecutionState,
        step: StepState,
        tool_result: Dict[str, Any]
    ) -> ReflectionResult:
        """
        Evaluate the result of a step execution.

        Args:
            state: Current execution state
            step: The step that just executed
            tool_result: Raw result from tool execution

        Returns:
            Detailed ReflectionResult with action decision
        """
        # Fast path: blocked by validator
        if step.status.value == "blocked":
            return ReflectionResult(
                status=ReflectionStatus.CRITICAL_FAILURE,
                confidence=1.0,
                reasoning=f"Step blocked by safety validator: {step.error}",
                next_action=NextAction.STOP,
                should_stop=True,
                recovery_suggestion="Review command safety and retry with safe parameters"
            )

        # Fast path: tool reported failure
        if not tool_result.get("success", False):
            error_msg = tool_result.get("message", "Unknown error")

            # Check if retryable
            if step.can_retry():
                return ReflectionResult(
                    status=ReflectionStatus.FAILURE,
                    confidence=0.8,
                    reasoning=f"Tool failed: {error_msg}",
                    next_action=NextAction.RETRY,
                    should_stop=False
                )
            else:
                return ReflectionResult(
                    status=ReflectionStatus.CRITICAL_FAILURE,
                    confidence=1.0,
                    reasoning=f"Tool failed after {step.attempts} attempts: {error_msg}",
                    next_action=NextAction.REPLAN,
                    should_stop=False,
                    recovery_suggestion="Consider alternative approach or manual intervention"
                )

        # Use LLM for nuanced evaluation
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(state, step, tool_result)

        try:
            raw_response = self.llm.generate(system_prompt, user_prompt)
            return self._parse_response(raw_response)
        except Exception as e:
            # Fallback on parse error
            return ReflectionResult(
                status=ReflectionStatus.SUCCESS,
                confidence=0.5,
                reasoning=f"Reflection parsing error, assuming success: {str(e)}",
                next_action=NextAction.CONTINUE,
                should_stop=False
            )

    def _build_system_prompt(self) -> str:
        """Build reflection system prompt."""
        return """You are an Execution Monitor AI. Evaluate step results and recommend next actions.

Respond with valid JSON:
{
    "status": "success | partial | failure | critical_failure",
    "confidence": 0.0-1.0,
    "reasoning": "Detailed analysis of what happened",
    "next_action": "continue | retry | replan | stop",
    "should_stop": true|false,
    "recovery_suggestion": "Optional guidance for recovery"
}

Status meanings:
- success: Output matches expected result, step completed
- partial: Output partially correct, may need adjustment
- failure: Step failed but recovery is possible
- critical_failure: Unrecoverable failure, stop execution

Next action meanings:
- continue: Proceed to next step
- retry: Retry current step (transient failure)
- replan: Generate new plan (approach wrong)
- stop: Execution complete or unsafe to continue

Confidence guide:
- 0.9-1.0: Very certain
- 0.7-0.89: Likely correct
- 0.5-0.69: Uncertain
- 0.0-0.49: Likely wrong

Be decisive. If output looks correct, mark success. If clearly wrong, mark failure."""

    def _build_user_prompt(
        self,
        state: ExecutionState,
        step: StepState,
        result: Dict[str, Any]
    ) -> str:
        """Build reflection user prompt."""
        completed = [s.to_dict() for s in state.completed_steps]
        remaining = [s.to_dict() for s in state.steps[state.current_step_index + 1:]]

        result_json = json.dumps(result, indent=2)

        return f"""Evaluate this execution step:

Goal: {state.goal}

Current step {step.id}: {step.action} with args {step.args}
Attempt: {step.attempts}/{step.max_attempts}

Tool result:
{result_json}

Completed steps: {json.dumps(completed, indent=2)}

Remaining steps: {json.dumps(remaining, indent=2)}

Has this step achieved its purpose? Should we continue, retry, replan, or stop?"""

    def _parse_response(self, raw_response: str) -> ReflectionResult:
        """Parse LLM reflection response."""
        import re

        try:
            # Try direct JSON parse
            data = json.loads(raw_response)
        except json.JSONDecodeError:
            # Try extract from markdown
            match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    data = {}
            else:
                # Try find any JSON structure
                match = re.search(r'(\{.*"status".*\})', raw_response, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        data = {}
                else:
                    data = {}

        # Map status
        status_str = data.get("status", "success").lower()
        try:
            status = ReflectionStatus(status_str)
        except ValueError:
            status = ReflectionStatus.SUCCESS

        # Map next action
        action_str = data.get("next_action", "continue").lower()
        try:
            next_action = NextAction(action_str)
        except ValueError:
            next_action = NextAction.CONTINUE

        # Check should_stop
        should_stop = data.get("should_stop", status == ReflectionStatus.CRITICAL_FAILURE)

        return ReflectionResult(
            status=status,
            confidence=data.get("confidence", 0.5),
            reasoning=data.get("reasoning", "No reasoning provided"),
            next_action=next_action,
            should_stop=should_stop,
            recovery_suggestion=data.get("recovery_suggestion")
        )

    def check_completion(self, state: ExecutionState) -> ReflectionResult:
        """Check overall execution completion."""
        completed = len(state.completed_steps)
        total = len(state.steps)
        failed = len(state.failed_steps)

        if failed > 0:
            return ReflectionResult(
                status=ReflectionStatus.FAILURE,
                confidence=1.0,
                reasoning=f"Execution completed with {failed} failures",
                next_action=NextAction.STOP,
                should_stop=True
            )

        if completed == total:
            return ReflectionResult(
                status=ReflectionStatus.SUCCESS,
                confidence=1.0,
                reasoning=f"All {total} steps completed successfully",
                next_action=NextAction.STOP,
                should_stop=True
            )

        return ReflectionResult(
            status=ReflectionStatus.PARTIAL,
            confidence=0.5,
            reasoning=f"Execution in progress: {completed}/{total} steps complete",
            next_action=NextAction.CONTINUE,
            should_stop=False
        )
