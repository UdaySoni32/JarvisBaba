"""Learning system for tracking task patterns and outcomes."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class PatternMemory:
    """Tracks success/failure patterns for learning and decision improvement."""

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "patterns.json",
            )

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._patterns: Dict[str, Dict[str, Any]] = {}

        self._load_patterns()

    def record_outcome(
        self,
        task_type: str,
        context: str,
        outcome: str,
        confidence: float = 1.0,
    ):
        """Record a task outcome (success/failure/partial)."""
        if outcome not in {"success", "failure", "partial"}:
            raise ValueError(f"Invalid outcome: {outcome}")

        with self._lock:
            pattern_key = f"{task_type}:{context}"

            if pattern_key not in self._patterns:
                self._patterns[pattern_key] = {
                    "pattern": task_type,
                    "context": context,
                    "success_count": 0,
                    "failure_count": 0,
                    "partial_count": 0,
                    "confidence": 1.0,
                    "last_occurrence": None,
                }

            pattern = self._patterns[pattern_key]

            if outcome == "success":
                pattern["success_count"] += 1
            elif outcome == "failure":
                pattern["failure_count"] += 1
            else:
                pattern["partial_count"] += 1

            pattern["last_occurrence"] = datetime.now().isoformat()

            total = pattern["success_count"] + pattern["failure_count"] + pattern["partial_count"]
            pattern["confidence"] = min(1.0, total / 10.0)

            self._persist_patterns()

    def get_pattern_confidence(self, task_type: str, context: str) -> float:
        """Get success confidence for a pattern (0-1)."""
        with self._lock:
            pattern_key = f"{task_type}:{context}"
            if pattern_key not in self._patterns:
                return 0.5

            pattern = self._patterns[pattern_key]
            total = pattern["success_count"] + pattern["failure_count"] + pattern["partial_count"]
            if total == 0:
                return 0.5

            success_rate = pattern["success_count"] / total
            return min(1.0, success_rate)

    def should_retry_pattern(self, task_type: str, context: str) -> bool:
        """Check if we should retry a pattern (based on success rate)."""
        confidence = self.get_pattern_confidence(task_type, context)
        return confidence > 0.3

    def list_patterns(self) -> List[Dict[str, Any]]:
        """List all tracked patterns."""
        with self._lock:
            return list(self._patterns.values())

    def clear_old_patterns(self, max_age_days: int = 30):
        """Remove patterns older than max_age_days."""
        import time

        with self._lock:
            cutoff_ts = time.time() - (max_age_days * 86400)
            to_remove = []

            for key, pattern in self._patterns.items():
                last_ts = datetime.fromisoformat(pattern["last_occurrence"]).timestamp()
                if last_ts < cutoff_ts:
                    to_remove.append(key)

            for key in to_remove:
                del self._patterns[key]

            if to_remove:
                self._persist_patterns()

    def _load_patterns(self):
        """Load patterns from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                self._patterns = {k: v for k, v in data.items()}
        except (json.JSONDecodeError, IOError):
            pass

    def _persist_patterns(self):
        """Persist patterns to disk."""
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self._patterns, f, indent=2)
        except IOError:
            pass


class FeedbackCollector:
    """Collects feedback from task execution for learning."""

    def __init__(self, pattern_memory: PatternMemory, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "logs",
                "learning.jsonl",
            )

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self.pattern_memory = pattern_memory
        self._lock = threading.RLock()

    def record_feedback(
        self,
        task_id: str,
        task_type: str,
        goal_id: Optional[str],
        context: str,
        outcome: str,
        execution_time: float,
        reasoning: str,
    ):
        """Record feedback from a completed task."""
        with self._lock:
            feedback = {
                "task_id": task_id,
                "task_type": task_type,
                "goal_id": goal_id,
                "context": context,
                "outcome": outcome,
                "execution_time": execution_time,
                "reasoning": reasoning,
                "timestamp": datetime.now().isoformat(),
            }

            self.pattern_memory.record_outcome(task_type, context, outcome)

            try:
                with open(self.storage_path, "a") as f:
                    json.dump(feedback, f)
                    f.write("\n")
            except IOError:
                pass

    def get_recent_feedback(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent feedback entries."""
        if not self.storage_path.exists():
            return []

        try:
            entries = []
            with open(self.storage_path, "r") as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
            return entries[-limit:]
        except (json.JSONDecodeError, IOError):
            return []
