"""
Execution State Machine - Formal state management for step execution.

Provides deterministic state transitions and tracking for multi-step plans.
"""
from enum import Enum, auto
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import json


class StepStatus(Enum):
    """Formal states for step execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class ExecutionMode(Enum):
    """Classification of user input."""
    SINGLE_STEP = "single_step"
    MULTI_STEP = "multi_step"


@dataclass
class StepState:
    """Complete state for a single step."""
    id: int
    action: str
    args: Dict[str, Any]
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "args": self.args,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "validation_errors": self.validation_errors
        }

    def can_retry(self) -> bool:
        """Check if step can be retried."""
        return self.attempts < self.max_attempts and self.status not in (StepStatus.SUCCESS, StepStatus.SKIPPED)

    def start(self):
        """Mark step as running."""
        self.status = StepStatus.RUNNING
        self.started_at = datetime.now()
        self.attempts += 1

    def complete(self, result: Any):
        """Mark step as successfully completed."""
        self.status = StepStatus.SUCCESS
        self.result = result
        self.error = None
        self.completed_at = datetime.now()

    def fail(self, error: str):
        """Mark step as failed."""
        self.status = StepStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    def mark_retry(self):
        """Mark step for retry."""
        if self.can_retry():
            self.status = StepStatus.RETRY
        else:
            self.status = StepStatus.FAILED

    def skip(self):
        """Mark step as skipped."""
        self.status = StepStatus.SKIPPED
        self.completed_at = datetime.now()

    def block(self, reason: str):
        """Mark step as blocked (safety/validation failure)."""
        self.status = StepStatus.BLOCKED
        self.error = reason
        self.validation_errors.append(reason)
        self.completed_at = datetime.now()


@dataclass
class ExecutionState:
    """Complete execution state for a plan."""
    goal: str
    steps: List[StepState]
    current_step_index: int = 0
    status: str = "pending"  # pending, running, complete, failed, aborted
    mode: Optional[ExecutionMode] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def current_step(self) -> Optional[StepState]:
        """Get current step state."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Check if execution is complete."""
        return self.status in ("complete", "failed", "aborted") or \
               all(s.status in (StepStatus.SUCCESS, StepStatus.SKIPPED) for s in self.steps)

    @property
    def has_failures(self) -> bool:
        """Check if any step failed."""
        return any(s.status == StepStatus.FAILED for s in self.steps)

    @property
    def has_blocked(self) -> bool:
        """Check if any step was blocked."""
        return any(s.status == StepStatus.BLOCKED for s in self.steps)

    @property
    def completed_steps(self) -> List[StepState]:
        """Get all completed steps."""
        return [s for s in self.steps if s.status == StepStatus.SUCCESS]

    @property
    def failed_steps(self) -> List[StepState]:
        """Get all failed steps."""
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def advance(self) -> bool:
        """Move to next step. Returns False if no more steps."""
        self.current_step_index += 1
        if self.current_step_index >= len(self.steps):
            if not self.has_failures and not self.has_blocked:
                self.status = "complete"
            else:
                self.status = "failed"
            self.completed_at = datetime.now()
            return False
        return True

    def abort(self, reason: str):
        """Abort execution."""
        self.status = "aborted"
        self.metadata["abort_reason"] = reason
        self.completed_at = datetime.now()

    def retry_current(self) -> bool:
        """Retry current step. Returns False if max retries exceeded."""
        current = self.current_step
        if not current:
            return False
        if current.can_retry():
            current.mark_retry()
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "mode": self.mode.value if self.mode else None,
            "current_step": self.current_step_index,
            "total_steps": len(self.steps),
            "completed_steps": len(self.completed_steps),
            "failed_steps": len(self.failed_steps),
            "has_blocked": self.has_blocked,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "steps": [s.to_dict() for s in self.steps],
            "metadata": self.metadata
        }


@dataclass
class ModeDecision:
    """Classification result for input mode."""
    mode: ExecutionMode
    reasoning: str
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "reasoning": self.reasoning,
            "confidence": self.confidence
        }
