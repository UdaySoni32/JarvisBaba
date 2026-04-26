"""Autonomous decision-making engine."""

from __future__ import annotations

import json
from typing import Dict, Optional, Any, List
from datetime import datetime

from core.context_aggregator import ContextAggregator
from core.tasks.task_manager import TaskManager
from models.llm import LLMInterface


class AutonomousDecision:
    """Output from decision engine."""

    def __init__(
        self,
        should_act: bool,
        reason: str,
        confidence: float,
        proposed_task: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
        requires_approval: bool = False,
        alignment_score: float = 0.5,
    ):
        self.should_act = should_act
        self.reason = reason
        self.confidence = confidence
        self.proposed_task = proposed_task or {}
        self.goal_id = goal_id
        self.requires_approval = requires_approval
        self.alignment_score = alignment_score
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_act": self.should_act,
            "reason": self.reason,
            "confidence": self.confidence,
            "proposed_task": self.proposed_task,
            "goal_id": self.goal_id,
            "requires_approval": self.requires_approval,
            "alignment_score": self.alignment_score,
            "timestamp": self.timestamp,
        }


class DecisionEngine:
    """Makes autonomous decisions based on system context, goals, and alignment."""

    def __init__(
        self,
        context_aggregator: ContextAggregator,
        task_manager: TaskManager,
        goal_manager = None,
        alignment_layer = None,
        pattern_memory = None,
        llm: Optional[LLMInterface] = None,
        confidence_threshold: float = 0.7,
    ):
        self.context = context_aggregator
        self.task_manager = task_manager
        self.goal_manager = goal_manager
        self.alignment = alignment_layer
        self.patterns = pattern_memory
        self.llm = llm
        self.confidence_threshold = float(confidence_threshold)

    def decide(self) -> AutonomousDecision:
        """Evaluate context and decide if action is needed."""
        ctx = self.context.get_context()

        decision = self._apply_heuristics(ctx)
        if decision.should_act:
            return decision

        decision = self._apply_goal_awareness(ctx)
        if decision.should_act:
            return decision

        if self.llm:
            decision = self._apply_llm_scoring(ctx)

        return decision

    def _apply_goal_awareness(self, context: Dict[str, Any]) -> AutonomousDecision:
        """Check if there are active goals that need task support."""
        if not self.goal_manager:
            return AutonomousDecision(should_act=False, reason="No goal manager", confidence=0.0)

        active_goals = self.goal_manager.list_active_goals()
        if not active_goals:
            return AutonomousDecision(should_act=False, reason="No active goals", confidence=0.0)

        for goal in active_goals:
            goal_tasks = self.task_manager.list_tasks_for_goal(goal.id)
            if not goal_tasks:
                return AutonomousDecision(
                    should_act=True,
                    reason=f"Goal '{goal.description}' has no tasks - consider creating support tasks",
                    confidence=0.5,
                    goal_id=goal.id,
                    proposed_task={
                        "goal": f"Support goal: {goal.description}",
                        "priority": goal.priority,
                        "mode": "background",
                    },
                )

        return AutonomousDecision(should_act=False, reason="Goals have support tasks", confidence=0.8)

    def _apply_heuristics(self, context: Dict[str, Any]) -> AutonomousDecision:
        """Apply conservative heuristics-based rules."""
        failed = context.get("failed_tasks", [])
        patterns = context.get("recurring_patterns", {})

        if failed and len(failed) > 0:
            decision = AutonomousDecision(
                should_act=True,
                reason=f"Detected {len(failed)} failed task(s) - consider retry or investigation",
                confidence=0.6,
                proposed_task={
                    "goal": f"Investigate and retry {len(failed)} failed task(s)",
                    "priority": 8,
                    "mode": "background",
                },
            )
            self._apply_approval_requirements(decision, "investigation")
            return decision

        high_failures = patterns.get("failed_task_count", 0) > 5
        if high_failures:
            decision = AutonomousDecision(
                should_act=True,
                reason="System has high failure rate - diagnostic task recommended",
                confidence=0.65,
                proposed_task={
                    "goal": "Run system diagnostics due to high failure rate",
                    "priority": 9,
                    "mode": "background",
                },
            )
            self._apply_approval_requirements(decision, "diagnostics")
            return decision

        return AutonomousDecision(
            should_act=False,
            reason="System is operating normally",
            confidence=0.95,
        )

    def _apply_approval_requirements(self, decision: AutonomousDecision, action_type: str):
        """Check if decision requires approval based on alignment layer."""
        if not self.alignment:
            return

        if self.alignment.requires_approval(action_type):
            decision.requires_approval = True

    def _apply_llm_scoring(self, context: Dict[str, Any]) -> AutonomousDecision:
        """Use LLM for more nuanced decision-making."""
        if not self.llm:
            return AutonomousDecision(should_act=False, reason="LLM unavailable", confidence=0.0)

        try:
            prompt = self._build_decision_prompt(context)
            response = self.llm.generate(
                "You are an autonomous decision engine for a task execution system.",
                prompt,
            )

            parsed = self._parse_llm_response(response)
            if parsed["should_act"] and parsed["confidence"] >= self.confidence_threshold:
                return AutonomousDecision(
                    should_act=True,
                    reason=parsed.get("reason", "LLM decision"),
                    confidence=parsed.get("confidence", 0.5),
                    proposed_task=parsed.get("proposed_task"),
                )
        except Exception:
            pass

        return AutonomousDecision(
            should_act=False,
            reason="No compelling reason to act",
            confidence=0.8,
        )

    def _build_decision_prompt(self, context: Dict[str, Any]) -> str:
        """Build prompt for LLM decision-making."""
        summary = json.dumps(context, indent=2, default=str)
        return f"""
Given this system context:

{summary}

Decide if the system should autonomously create a task.

Guidelines:
- Only suggest tasks if there's a clear operational benefit
- Avoid redundant or speculative tasks
- Be conservative - safety first
- High confidence only for obvious needs

Respond with JSON:
{{
  "should_act": true|false,
  "reason": "clear explanation",
  "confidence": 0.0-1.0,
  "proposed_task": {{
    "goal": "task goal if should_act",
    "priority": 5,
    "mode": "background"
  }}
}}
"""

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM JSON response."""
        try:
            parsed = json.loads(response)
            return {
                "should_act": bool(parsed.get("should_act")),
                "reason": str(parsed.get("reason", "")),
                "confidence": float(parsed.get("confidence", 0.0)),
                "proposed_task": parsed.get("proposed_task", {}),
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            return {"should_act": False, "reason": "Invalid LLM response", "confidence": 0.0}
