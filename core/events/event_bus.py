"""Thread-safe event bus for task triggers."""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional


class EventBus:
    """Manages event subscriptions and dispatching."""

    def __init__(self):
        self._lock = threading.RLock()
        self._listeners: Dict[str, List[Callable[[str], None]]] = {}
        self._event_history: List[Dict[str, str]] = []
        self._max_history = 100

    def subscribe(self, event_name: str, callback: Callable[[str], None]) -> None:
        """Register a callback for an event."""
        with self._lock:
            if event_name not in self._listeners:
                self._listeners[event_name] = []
            if callback not in self._listeners[event_name]:
                self._listeners[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[str], None]) -> bool:
        """Unregister a callback. Returns True if found and removed."""
        with self._lock:
            if event_name in self._listeners:
                try:
                    self._listeners[event_name].remove(callback)
                    return True
                except ValueError:
                    return False
        return False

    def publish(self, event_name: str, payload: Optional[str] = None) -> None:
        """Trigger an event, calling all registered callbacks."""
        with self._lock:
            callbacks = list(self._listeners.get(event_name, []))
            self._event_history.append({"event": event_name, "payload": payload or ""})
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

        for callback in callbacks:
            try:
                callback(payload or "")
            except Exception:
                pass

    def listeners_for(self, event_name: str) -> int:
        """Count registered listeners for an event."""
        with self._lock:
            return len(self._listeners.get(event_name, []))

    def all_events(self) -> Dict[str, int]:
        """Return count of listeners per event."""
        with self._lock:
            return {name: len(cbs) for name, cbs in self._listeners.items() if cbs}

    def recent_events(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent event history."""
        with self._lock:
            return list(self._event_history[-limit:])
