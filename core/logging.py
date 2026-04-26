"""
Logging module - Structured execution logging for traceability.

Provides persistent logs of all agent activities for debugging and auditing.
"""
import json
import os
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class ExecutionLogger:
    """
    Structured logger for agent execution.
    Writes logs to /logs/ directory with timestamps.
    """

    def __init__(self, log_dir: str = None):
        """
        Initialize logger.

        Args:
            log_dir: Directory for log files. Defaults to ./logs/
        """
        if log_dir is None:
            log_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "logs"
            )

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"jarvis_{self.session_id}.jsonl"
        self._lock = threading.Lock()

        self._write_header()

    def _write_header(self):
        """Write session header."""
        self._log({
            "type": "session_start",
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id
        })

    def _log(self, entry: Dict[str, Any]):
        """Write a log entry."""
        entry["_timestamp"] = datetime.now().isoformat()
        entry["_session"] = self.session_id

        with self._lock:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")

    def _attach_task_id(self, payload: Dict[str, Any], task_id: Optional[str] = None) -> Dict[str, Any]:
        if task_id:
            payload["task_id"] = task_id
        return payload

    def log_input(self, user_input: str, mode: str, reasoning: str, task_id: Optional[str] = None):
        """Log user input classification."""
        self._log(self._attach_task_id({
            "type": "input",
            "input": user_input,
            "mode": mode,
            "reasoning": reasoning
        }, task_id))

    def log_plan(self, goal: str, plan_data: Dict, tool_count: int, task_id: Optional[str] = None):
        """Log generated plan."""
        self._log(self._attach_task_id({
            "type": "plan",
            "goal": goal,
            "steps_count": len(plan_data.get("steps", [])),
            "tools_count": tool_count,
            "plan": plan_data
        }, task_id))

    def log_step_start(self, step_id: int, action: str, args: Dict, attempt: int, task_id: Optional[str] = None):
        """Log step execution start."""
        self._log(self._attach_task_id({
            "type": "step_start",
            "step_id": step_id,
            "action": action,
            "args": args,
            "attempt": attempt
        }, task_id))

    def log_step_result(
        self,
        step_id: int,
        success: bool,
        result: Any,
        error: Optional[str] = None,
        task_id: Optional[str] = None
    ):
        """Log step execution result."""
        self._log(self._attach_task_id({
            "type": "step_result",
            "step_id": step_id,
            "success": success,
            "result": result,
            "error": error
        }, task_id))

    def log_reflection(
        self,
        step_id: int,
        status: str,
        confidence: float,
        next_action: str,
        reasoning: str,
        task_id: Optional[str] = None
    ):
        """Log reflection decision."""
        self._log(self._attach_task_id({
            "type": "reflection",
            "step_id": step_id,
            "status": status,
            "confidence": confidence,
            "next_action": next_action,
            "reasoning": reasoning
        }, task_id))

    def log_validation(
        self,
        step_id: int,
        is_valid: bool,
        errors: list,
        blocked: bool = False,
        task_id: Optional[str] = None
    ):
        """Log validation result."""
        self._log(self._attach_task_id({
            "type": "validation",
            "step_id": step_id,
            "is_valid": is_valid,
            "errors": errors,
            "blocked": blocked
        }, task_id))

    def log_replan(self, old_plan: Dict, new_plan: Dict, reason: str, task_id: Optional[str] = None):
        """Log replanning event."""
        self._log(self._attach_task_id({
            "type": "replan",
            "reason": reason,
            "old_step_count": len(old_plan.get("steps", [])),
            "new_step_count": len(new_plan.get("steps", []))
        }, task_id))

    def log_completion(
        self,
        final_state: str,
        completed: int,
        failed: int,
        total: int,
        task_id: Optional[str] = None
    ):
        """Log execution completion."""
        self._log(self._attach_task_id({
            "type": "completion",
            "final_state": final_state,
            "completed_steps": completed,
            "failed_steps": failed,
            "total_steps": total
        }, task_id))

    def log_error(
        self,
        error_type: str,
        message: str,
        context: Optional[Dict] = None,
        task_id: Optional[str] = None
    ):
        """Log an error."""
        self._log(self._attach_task_id({
            "type": "error",
            "error_type": error_type,
            "message": message,
            "context": context or {}
        }, task_id))

    def log_task_event(self, task_id: str, event: str, payload: Optional[Dict[str, Any]] = None):
        """Log task lifecycle events."""
        data = payload or {}
        self._log(self._attach_task_id({
            "type": "task_event",
            "event": event,
            "payload": data,
        }, task_id))

    def get_log_path(self) -> str:
        """Get the path to the current log file."""
        return str(self.log_file)

    def log_autonomy_decision(self, decision: Dict[str, Any], created_task_id: Optional[str] = None):
        """Log autonomous decision."""
        entry = self._attach_task_id({
            "type": "autonomy_decision",
            "decision": decision,
            "created_task_id": created_task_id,
        }, created_task_id)
        self._log(entry)

    def read_logs(self) -> list:
        """Read all logs from current session."""
        logs = []
        if self.log_file.exists():
            with open(self.log_file, "r") as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        return logs

    def summary(self) -> Dict[str, Any]:
        """Generate execution summary from logs."""
        logs = self.read_logs()

        summary = {
            "session_id": self.session_id,
            "total_entries": len(logs),
            "by_type": {},
            "errors": [],
            "plan_generated": False,
            "steps_executed": 0,
            "steps_failed": 0,
            "replans": 0
        }

        for entry in logs:
            entry_type = entry.get("type", "unknown")
            summary["by_type"][entry_type] = summary["by_type"].get(entry_type, 0) + 1

            if entry_type == "error":
                summary["errors"].append(entry.get("message"))

            if entry_type == "plan":
                summary["plan_generated"] = True

            if entry_type == "step_result":
                summary["steps_executed"] += 1
                if not entry.get("success"):
                    summary["steps_failed"] += 1

            if entry_type == "replan":
                summary["replans"] += 1

        return summary
