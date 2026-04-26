"""
Core Agent module - LLM decision making with structured output.
Updated with intelligent mode classification.
"""
import json
import re
from typing import Optional
from models.llm import LLMInterface
from core.memory.short_term import ShortTermMemory
from core.state import ModeDecision, ExecutionMode
from core.schedule_parser import ScheduleParser


class AgentDecision:
    """Structured output from the agent."""

    def __init__(
        self,
        thought: str,
        action: Optional[str],
        args: dict,
        response: Optional[str] = None
    ):
        self.thought = thought
        self.action = action
        self.args = args
        self.response = response

    @property
    def requires_tool(self) -> bool:
        return self.action is not None

    def to_dict(self) -> dict:
        return {
            "thought": self.thought,
            "action": self.action,
            "args": self.args,
            "response": self.response
        }


class TaskIntentDecision:
    """Structured task intent classification."""

    def __init__(
        self,
        should_create_task: bool,
        mode: str,
        reasoning: str,
        confidence: float = 0.0
    ):
        self.should_create_task = should_create_task
        self.mode = mode
        self.reasoning = reasoning
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "should_create_task": self.should_create_task,
            "mode": self.mode,
            "reasoning": self.reasoning,
            "confidence": self.confidence
        }


class Agent:
    """
    The Agent decides whether to respond directly or use tools.
    Includes intelligent mode classification for single vs multi-step.
    """

    def __init__(
        self,
        llm: LLMInterface,
        memory: ShortTermMemory,
        available_tools: Optional[list] = None
    ):
        self.llm = llm
        self.memory = memory
        self.available_tools = available_tools or []
        self._autonomy_mode = "off"  # off, suggest, assist, full

    def _build_system_prompt(self) -> str:
        """Build system prompt for agent."""
        tools_text = "\n".join([
            f"- {t['name']}: {t['description']}"
            for t in self.available_tools
        ])

        return f"""You are Jarvis, a helpful AI assistant with tool access.

Available tools:
{tools_text}

Respond with JSON:
{{
    "thought": "Your reasoning",
    "action": "tool_name or null",
    "args": {{"param": "value"}} or {{}},
    "response": "Text if action is null"
}}

Rules:
- Use action only for: open_app, run_command
- Set action to null for greetings, questions, conversation
- Think step by step"""

    def _build_mode_prompt(self) -> str:
        """Build system prompt for mode classification."""
        return """You are a Task Classifier. Determine if user input requires single-step or multi-step execution.

Multi-step indicators:
- Multiple distinct actions ("check logs AND restart service")
- Sequential tasks ("first X, then Y")
- Complex workflows requiring coordination
- Tasks with dependencies between actions

Single-step indicators:
- One simple command ("open firefox")
- Questions ("what time is it")
- Instructions for one tool only
- Conversations

Respond with JSON:
{
    "mode": "single_step | multi_step",
    "reasoning": "Why this classification",
    "confidence": 0.0-1.0
}"""

    def classify_mode(self, user_input: str) -> ModeDecision:
        """
        Classify user input into single_step or multi_step mode.
        Uses LLM for intelligent classification.
        """
        system_prompt = self._build_mode_prompt()
        user_prompt = f"Classify this input: \"{user_input}\""

        try:
            raw_response = self.llm.generate(system_prompt, user_prompt)
            parsed = self._parse_response(raw_response)

            mode_str = parsed.get("mode", "single_step").lower()
            try:
                mode = ExecutionMode(mode_str.replace("-", "_"))
            except ValueError:
                mode = ExecutionMode.SINGLE_STEP

            return ModeDecision(
                mode=mode,
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                confidence=parsed.get("confidence", 0.5)
            )

        except Exception as e:
            # Fallback to single_step on error
            return ModeDecision(
                mode=ExecutionMode.SINGLE_STEP,
                reasoning=f"Classification error, defaulting to single_step: {str(e)}",
                confidence=0.0
            )

    def _build_task_intent_prompt(self) -> str:
        """Build prompt for task intent and mode detection."""
        return """You are a Task Router for an agent runtime.

Decide if this input should create a managed task object.

Create a task when:
- User asks for multi-step execution or queued workflow
- User asks explicitly for background/deferred execution

Do NOT create a task when:
- It's small talk or a direct question
- It's a simple one-shot response with no execution needed

Respond with JSON:
{
  "should_create_task": true|false,
  "mode": "foreground|background",
  "reasoning": "short reason",
  "confidence": 0.0-1.0
}"""

    def classify_task_intent(self, user_input: str) -> TaskIntentDecision:
        """Classify whether input should become a managed task."""
        text = user_input.lower()
        background_markers = [
            "background", "in background", "defer", "later", "queue", "asynchronously", "async"
        ]
        task_markers = [
            "task", "workflow", "and then", "first", "then", "after that", "steps", "plan and execute"
        ]

        heuristic_mode = "background" if any(m in text for m in background_markers) else "foreground"
        heuristic_create = any(m in text for m in task_markers) or heuristic_mode == "background"
        heuristic = TaskIntentDecision(
            should_create_task=heuristic_create,
            mode=heuristic_mode,
            reasoning="Heuristic task routing",
            confidence=0.6 if heuristic_create else 0.4
        )

        try:
            raw_response = self.llm.generate(
                self._build_task_intent_prompt(),
                f"Classify this input: \"{user_input}\"",
            )
            parsed = self._parse_response(raw_response)
            if "should_create_task" not in parsed:
                return heuristic

            mode = str(parsed.get("mode", heuristic.mode)).lower()
            if mode not in {"foreground", "background"}:
                mode = heuristic.mode

            return TaskIntentDecision(
                should_create_task=bool(parsed.get("should_create_task")),
                mode=mode,
                reasoning=parsed.get("reasoning", "Task routing decision"),
                confidence=parsed.get("confidence", 0.5),
            )
        except Exception:
            return heuristic

    def classify_schedule_intent(self, user_input: str) -> tuple:
        """
        Parse user input for scheduling and event directives.

        Returns (schedule_dict, trigger_dict) or (None, None) if none found.
        """
        return ScheduleParser.parse_schedule_intent(user_input)

    def set_autonomy_mode(self, mode: str) -> bool:
        """Set autonomy mode: off, suggest, assist, or full."""
        if mode.lower() not in {"off", "suggest", "assist", "full"}:
            return False
        self._autonomy_mode = mode.lower()
        return True

    def get_autonomy_mode(self) -> str:
        """Get current autonomy mode."""
        return self._autonomy_mode

    def is_autonomy_enabled(self) -> bool:
        """Check if autonomy is enabled (compatibility method)."""
        return self._autonomy_mode != "off"

    def enable_autonomy(self) -> None:
        """Enable autonomy with FULL mode (compatibility)."""
        self._autonomy_mode = "full"

    def disable_autonomy(self) -> None:
        """Disable autonomy (set to OFF mode)."""
        self._autonomy_mode = "off"

    def decide(self, user_input: str) -> AgentDecision:
        """Process user input and return decision."""
        self.memory.add_message("user", user_input)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(user_input)

        try:
            raw_response = self.llm.generate(system_prompt, user_prompt)
            parsed = self._parse_response(raw_response)

            return AgentDecision(
                thought=parsed.get("thought", ""),
                action=parsed.get("action"),
                args=parsed.get("args", {}),
                response=parsed.get("response")
            )

        except Exception as e:
            return AgentDecision(
                thought=f"Error during LLM processing: {str(e)}",
                action=None,
                args={},
                response=f"I encountered an error: {str(e)}"
            )

    def _build_user_prompt(self, user_input: str) -> str:
        """Build user prompt with conversation context."""
        context = self.memory.get_context()
        history = "\n".join([
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in context
        ])

        return f"""Conversation history:
{history}

Current user input: {user_input}

Respond with the JSON format specified."""

    def _parse_response(self, raw_response: str) -> dict:
        """Parse LLM response into structured dict."""
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

        # Try to find any JSON-like structure
        match = re.search(r'(\{.*"id".*\})', raw_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Fallback
        return {
            "thought": "Failed to parse structured output",
            "action": None,
            "args": {},
            "response": raw_response.strip()
        }
