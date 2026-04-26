"""
Short-term memory - Store recent conversation context and execution state.
Enhanced for multi-step planning with goal, steps, and results tracking.
"""
from collections import deque
from typing import List, Dict, Optional, Any
import json


class ShortTermMemory:
    """
    Stores context for multi-turn conversations and multi-step plans.
    Tracks: messages, current goal, plan steps, and execution history.
    """

    def __init__(self, max_messages: int = 20):
        """
        Initialize short-term memory.

        Args:
            max_messages: Maximum number of messages to retain
        """
        self.max_messages = max_messages
        self.messages: deque = deque(maxlen=max_messages)

        # Multi-step execution state
        self.current_goal: Optional[str] = None
        self.current_plan: Optional[Dict] = None
        self.execution_history: List[Dict] = []

    def add_message(self, role: str, content: str) -> None:
        """
        Add a message to memory.

        Args:
            role: 'user', 'assistant', or 'system'
            content: The message content
        """
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": None
        })

    def add_tool_result(self, tool_name: str, result: dict) -> None:
        """Add a tool execution result to memory."""
        self.messages.append({
            "role": "system",
            "content": f"Tool '{tool_name}' executed: {result.get('message', '')}",
            "result": result
        })

    def add_step_result(self, step_id: int, action: str, result: Dict) -> None:
        """Add a plan step execution result to memory and history."""
        record = {
            "step_id": step_id,
            "action": action,
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "output": result.get("result")
        }
        self.execution_history.append(record)

        # Also add as a message
        status = "succeeded" if result.get("success") else "failed"
        self.add_message(
            "system",
            f"Step {step_id} ({action}) {status}: {result.get('message', '')}"
        )

    def set_goal(self, goal: str) -> None:
        """Set the current execution goal."""
        self.current_goal = goal
        self.add_message("system", f"New goal: {goal}")

    def set_plan(self, plan: Dict) -> None:
        """Store the current execution plan."""
        self.current_plan = plan
        steps_count = len(plan.get("steps", []))
        self.add_message("system", f"Plan created with {steps_count} steps")

    def get_execution_summary(self) -> str:
        """Get a summary of execution history."""
        if not self.execution_history:
            return "No execution history"

        lines = []
        for record in self.execution_history:
            status = "" if record["success"] else "[FAIL]"
            lines.append(
                f"Step {record['step_id']}: {record['action']} {status}"
            )
        return "\n".join(lines)

    def get_context(self, n: Optional[int] = None) -> List[Dict]:
        """
        Get the most recent messages.

        Args:
            n: Number of messages to return (default: all)

        Returns:
            List of message dictionaries
        """
        if n is None:
            return list(self.messages)
        return list(self.messages)[-n:]

    def get_plan_context(self) -> str:
        """Get formatted plan context for LLM."""
        parts = []

        if self.current_goal:
            parts.append(f"Goal: {self.current_goal}")

        if self.current_plan:
            parts.append(f"Plan: {json.dumps(self.current_plan, indent=2)}")

        if self.execution_history:
            parts.append("Execution History:")
            for record in self.execution_history:
                status = "OK" if record["success"] else "FAIL"
                parts.append(f"  Step {record['step_id']} ({record['action']}): {status}")

        return "\n".join(parts)

    def clear(self) -> None:
        """Clear all messages and execution state."""
        self.messages.clear()
        self.current_goal = None
        self.current_plan = None
        self.execution_history = []

    def clear_execution_state(self) -> None:
        """Clear only execution state (plan, goal, history) but keep messages."""
        self.current_goal = None
        self.current_plan = None
        self.execution_history = []

    def get_conversation_text(self) -> str:
        """Get the conversation as formatted text."""
        lines = []
        for msg in self.messages:
            role = msg["role"].capitalize()
            content = msg["content"]
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Export memory state as dictionary."""
        return {
            "messages": list(self.messages),
            "current_goal": self.current_goal,
            "current_plan": self.current_plan,
            "execution_history": self.execution_history
        }
