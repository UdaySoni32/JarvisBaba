"""Alignment layer for user preferences and safety rules."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class AlignmentLayer:
    """Enforces hard rules and soft preferences for autonomous decisions."""

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "alignment.json",
            )

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()

        self.hard_rules: Dict[str, bool] = {
            "require_approval_for_installs": True,
            "require_approval_for_system_commands": True,
            "require_approval_for_api_calls": True,
            "require_approval_for_destructive_ops": True,
            "allow_file_operations": True,
            "allow_task_creation": True,
        }

        self.forbidden_actions: Set[str] = {
            "rm -rf",
            "sudo reboot",
            "shutdown",
            "pkill -9",
            ":(){ :|: & };:",
        }

        self.soft_preferences: Dict[str, Any] = {
            "prefer_local_models": True,
            "batch_operations": True,
            "auto_retry_on_failure": False,
            "max_approval_wait_seconds": 300,
        }

        self._load_alignment()

    def requires_approval(self, action_type: str) -> bool:
        """Check if an action requires approval."""
        with self._lock:
            rule_key = f"require_approval_for_{action_type}"
            return self.hard_rules.get(rule_key, False)

    def is_forbidden(self, command: str) -> bool:
        """Check if a command is forbidden."""
        with self._lock:
            for forbidden in self.forbidden_actions:
                if forbidden.lower() in command.lower():
                    return True
            return False

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a soft preference value."""
        with self._lock:
            return self.soft_preferences.get(key, default)

    def set_hard_rule(self, rule_name: str, value: bool):
        """Update a hard rule."""
        with self._lock:
            self.hard_rules[rule_name] = bool(value)
            self._persist_alignment()

    def set_preference(self, key: str, value: Any):
        """Update a soft preference."""
        with self._lock:
            self.soft_preferences[key] = value
            self._persist_alignment()

    def add_forbidden_action(self, action: str):
        """Add a forbidden action pattern."""
        with self._lock:
            self.forbidden_actions.add(action)
            self._persist_alignment()

    def remove_forbidden_action(self, action: str):
        """Remove a forbidden action pattern."""
        with self._lock:
            self.forbidden_actions.discard(action)
            self._persist_alignment()

    def validate_command(self, command: str) -> tuple[bool, Optional[str]]:
        """Validate a command against rules. Returns (valid, reason_if_invalid)."""
        with self._lock:
            if self.is_forbidden(command):
                return False, f"Command contains forbidden pattern"
            return True, None

    def _load_alignment(self):
        """Load alignment config from disk."""
        if not self.storage_path.exists():
            self._persist_alignment()
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                self.hard_rules.update(data.get("hard_rules", {}))
                self.soft_preferences.update(data.get("soft_preferences", {}))
                self.forbidden_actions.update(data.get("forbidden_actions", []))
        except (json.JSONDecodeError, IOError):
            pass

    def _persist_alignment(self):
        """Persist alignment config to disk."""
        try:
            data = {
                "hard_rules": self.hard_rules,
                "soft_preferences": self.soft_preferences,
                "forbidden_actions": list(self.forbidden_actions),
            }
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass
