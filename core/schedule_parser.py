"""Parse natural language into scheduling and event configurations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple


class ScheduleParser:
    """Converts user input into schedule and trigger definitions."""

    @staticmethod
    def parse_schedule_intent(user_input: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Parse user input for scheduling/event directives.

        Returns (schedule, trigger) or (None, None) if no schedule/event found.
        """
        text = user_input.lower()

        schedule = ScheduleParser._extract_schedule(text)
        trigger = ScheduleParser._extract_trigger(text)

        return schedule, trigger

    @staticmethod
    def _extract_schedule(text: str) -> Optional[Dict[str, Any]]:
        """Extract schedule configuration from text."""
        if "every" in text or "repeat" in text:
            interval = ScheduleParser._parse_interval(text)
            if interval:
                return {"type": "recurring", "interval": interval, "run_at": None}

        if any(x in text for x in ["in ", "after ", "at ", "later"]):
            delay = ScheduleParser._parse_delay(text)
            if delay:
                run_at = (datetime.now() + timedelta(seconds=delay)).isoformat()
                return {"type": "delayed", "run_at": run_at, "interval": None}

        return None

    @staticmethod
    def _extract_trigger(text: str) -> Optional[Dict[str, Any]]:
        """Extract event trigger from text."""
        keywords = {
            "when": ["when"],
            "on": ["on"],
            "if": ["if"],
        }

        for trigger_type, kw_list in keywords.items():
            for kw in kw_list:
                if f" {kw} " in f" {text} ":
                    idx = text.find(kw)
                    if idx >= 0:
                        rest = text[idx + len(kw):].strip()
                        event_name = ScheduleParser._extract_event_name(rest)
                        if event_name:
                            return {"type": "event", "event_name": event_name}

        return None

    @staticmethod
    def _parse_interval(text: str) -> Optional[int]:
        """Extract recurring interval in seconds."""
        import re

        patterns = [
            (r'every\s+(\d+)\s+seconds?', 1),
            (r'every\s+(\d+)\s+minutes?', 60),
            (r'every\s+(\d+)\s+hours?', 3600),
            (r'every\s+(\d+)\s+days?', 86400),
        ]

        for pattern, multiplier in patterns:
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                return value * multiplier

        # Handle "every hour", "every minute", "every second", "every day" without number
        default_patterns = [
            (r'every\s+seconds?', 1),
            (r'every\s+minutes?', 60),
            (r'every\s+hours?', 3600),
            (r'every\s+days?', 86400),
        ]

        for pattern, interval in default_patterns:
            if re.search(pattern, text):
                return interval

        return None

    @staticmethod
    def _parse_delay(text: str) -> Optional[int]:
        """Extract delay in seconds from text."""
        import re

        patterns = [
            (r'in\s+(\d+)\s+seconds?', 1),
            (r'in\s+(\d+)\s+minutes?', 60),
            (r'in\s+(\d+)\s+hours?', 3600),
            (r'after\s+(\d+)\s+seconds?', 1),
            (r'after\s+(\d+)\s+minutes?', 60),
            (r'after\s+(\d+)\s+hours?', 3600),
        ]

        for pattern, multiplier in patterns:
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                return value * multiplier

        return None

    @staticmethod
    def _extract_event_name(text: str) -> Optional[str]:
        """Extract event name from text."""
        import re

        tokens = re.split(r'[.,;!?]', text)
        for token in tokens:
            token = token.strip()
            if token and len(token) < 50:
                return token.lower()

        return None
