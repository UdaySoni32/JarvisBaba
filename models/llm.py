"""
LLM Interface - Abstract wrapper for different LLM providers.
Supports local (Ollama) and API-based (Anthropic, OpenAI) models.
Includes DeterministicLLM for testing.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import json


class LLMInterface(ABC):
    """Abstract base class for LLM implementations."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a response from the LLM."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this LLM implementation."""
        pass


class DeterministicLLM(LLMInterface):
    """
    Deterministic LLM for testing.
    Returns predictable responses based on seeded random or fixed outputs.
    Ensures tests are reproducible.
    """

    def __init__(
        self,
        seed: int = 42,
        fixed_response: Optional[str] = None,
        fixed_plan: bool = False,
        noop: bool = False,
        fail_every: Optional[int] = None
    ):
        self.seed = seed
        self.fixed_response = fixed_response
        self.fixed_plan = fixed_plan
        self.noop = noop
        self.fail_every = fail_every
        self.call_count = 0

    @property
    def name(self) -> str:
        if self.noop:
            return "DeterministicLLM (NoOp)"
        if self.fixed_response:
            return "DeterministicLLM (Fixed)"
        if self.fixed_plan:
            return "DeterministicLLM (Planning)"
        return "DeterministicLLM (Seeded)"

    @property
    def is_deterministic(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate deterministic response."""
        self.call_count += 1

        if self.noop:
            return self._noop_response(system_prompt)

        if self.fixed_response:
            return self.fixed_response

        if self.fail_every and self.call_count % self.fail_every == 0:
            return json.dumps({
                "thought": "Simulated failure",
                "action": None,
                "args": {},
                "response": "I cannot process this request."
            })

        # Detect mode from system prompt
        is_planner = "Planner" in system_prompt or "plan" in system_prompt.lower()
        is_reflector = "Monitor" in system_prompt or "reflection" in system_prompt.lower()

        if is_planner:
            return self._generate_plan_response(user_prompt)
        elif is_reflector:
            return self._generate_reflection_response()
        else:
            return self._generate_agent_response(user_prompt)

    def _noop_response(self, system_prompt: str) -> str:
        """Return minimal valid response."""
        if "Planner" in system_prompt:
            return json.dumps({"goal": "Test", "steps": []})
        if "Monitor" in system_prompt:
            return json.dumps({
                "status": "success",
                "confidence": 0.9,
                "reasoning": "No-op mode",
                "next_action": "continue",
                "should_stop": False
            })
        return json.dumps({
            "thought": "No-op",
            "action": None,
            "args": {},
            "response": "Acknowledged."
        })

    def _generate_plan_response(self, user_prompt: str) -> str:
        """Generate a deterministic plan."""
        user_lower = user_prompt.lower()

        # Multi-step pattern
        if "and then" in user_lower or "and" in user_lower:
            return json.dumps({
                "goal": "Multi-step task",
                "steps": [
                    {"id": 1, "action": "run_command", "args": {"command": "echo step1"}},
                    {"id": 2, "action": "run_command", "args": {"command": "echo step2"}}
                ]
            })

        # Single step
        return json.dumps({
            "goal": "Single task",
            "steps": [
                {"id": 1, "action": "run_command", "args": {"command": "echo done"}}
            ]
        })

    def _generate_reflection_response(self) -> str:
        """Generate a deterministic reflection."""
        return json.dumps({
            "status": "success",
            "confidence": 0.9,
            "reasoning": "Step executed successfully",
            "next_action": "continue",
            "should_stop": False,
            "recovery_suggestion": None
        })

    def _generate_agent_response(self, user_input: str) -> str:
        """Generate a deterministic agent response."""
        user_lower = user_input.lower()

        if any(w in user_lower for w in ["open", "launch", "start"]):
            return json.dumps({
                "thought": "Open something",
                "action": "open_app",
                "args": {"app_name": "terminal"},
                "response": None
            })

        if any(w in user_lower for w in ["run", "execute", "command", "ls", "pwd"]):
            cmd = user_input.split()[-1] if " " in user_input else user_input
            return json.dumps({
                "thought": "Run command",
                "action": "run_command",
                "args": {"command": cmd},
                "response": None
            })

        return json.dumps({
            "thought": "Direct response",
            "action": None,
            "args": {},
            "response": f"Deterministic: {user_input}"
        })


class FakeLLM(LLMInterface):
    """
    Fake LLM for testing the pipeline without API calls.
    Simulates structured output for development.
    Detects planning vs agent mode from prompt content.
    """

    def __init__(self):
        self.call_count = 0

    @property
    def name(self) -> str:
        return "FakeLLM (Test Mode)"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Simulate LLM responses based on user input keywords."""
        self.call_count += 1

        # Detect mode
        is_planner = "Planner" in system_prompt or "plan" in system_prompt.lower()
        is_reflector = "Monitor" in system_prompt or "reflection" in system_prompt.lower()
        is_mode_classifier = "Classifier" in system_prompt

        user_input = self._extract_input(user_prompt)
        user_lower = user_input.lower()

        if is_mode_classifier:
            return self._generate_mode_classification(user_input, user_lower)

        if is_planner:
            return self._generate_plan(user_input, user_lower)

        if is_reflector:
            return self._generate_reflection(user_prompt)

        return self._generate_agent_response(user_input, user_lower)

    def _extract_input(self, user_prompt: str) -> str:
        """Extract user request from prompt."""
        if 'Create a plan' in user_prompt:
            parts = user_prompt.split('Create a plan')
            if len(parts) > 1:
                text = parts[1].split('\n')[0].strip().strip('"').strip("'")
                return text

        if "Current user input:" in user_prompt:
            parts = user_prompt.split("Current user input:")
            if len(parts) > 1:
                return parts[-1].split("Respond")[0].strip()

        if "Classify" in user_prompt:
            parts = user_prompt.split('"')
            if len(parts) >= 2:
                return parts[1]

        return user_prompt[:100].strip()

    def _generate_mode_classification(self, user_input: str, user_lower: str) -> str:
        """Classify into single_step or multi_step."""
        multi_indicators = ["and then", "and", "first", "steps", "multi", "sequence"]
        if any(ind in user_lower for ind in multi_indicators):
            return json.dumps({
                "mode": "multi_step",
                "reasoning": f"Input '{user_input}' suggests multiple actions",
                "confidence": 0.85
            })
        return json.dumps({
            "mode": "single_step",
            "reasoning": f"Input '{user_input}' is simple/conversational",
            "confidence": 0.9
        })

    def _generate_plan(self, user_input: str, user_lower: str) -> str:
        """Generate a plan."""
        steps = []

        if "and then" in user_lower or "and" in user_lower:
            if "open" in user_lower:
                steps.append({"id": 1, "action": "open_app", "args": {"app_name": "firefox"}})
            if "run" in user_lower or "pwd" in user_lower or "ls" in user_lower:
                steps.append({"id": 2, "action": "run_command", "args": {"command": "pwd"}})

        if not steps:
            cmd = "echo 'no specific plan'"
            for c in ["ls", "pwd", "echo", "cat"]:
                if c in user_lower:
                    cmd = user_lower[user_lower.find(c):].split()[0]
                    break
            steps = [{"id": 1, "action": "run_command", "args": {"command": cmd}}]

        return json.dumps({
            "goal": f"Accomplish: {user_input}",
            "steps": steps
        })

    def _generate_reflection(self, full_prompt: str) -> str:
        """Generate reflection."""
        if "failed" in full_prompt.lower():
            return json.dumps({
                "status": "failure",
                "confidence": 0.8,
                "reasoning": "Tool execution failed",
                "next_action": "retry",
                "should_stop": False
            })

        if "blocked" in full_prompt.lower():
            return json.dumps({
                "status": "critical_failure",
                "confidence": 1.0,
                "reasoning": "Command blocked by safety validator",
                "next_action": "stop",
                "should_stop": True
            })

        return json.dumps({
            "status": "success",
            "confidence": 0.9,
            "reasoning": "Step executed successfully",
            "next_action": "continue",
            "should_stop": False
        })

    def _generate_agent_response(self, user_input: str, user_lower: str) -> str:
        """Generate agent response."""
        if any(w in user_lower for w in ["open", "launch", "start"]):
            words = user_lower.split()
            app = "terminal"
            for i, w in enumerate(words):
                if w in ["open", "launch", "start"] and i + 1 < len(words):
                    app = words[i + 1]
                    break
            return json.dumps({
                "thought": f"Open {app}",
                "action": "open_app",
                "args": {"app_name": app},
                "response": None
            })

        if any(w in user_lower for w in ["run", "execute", "ls", "pwd", "echo", "command"]):
            cmd = user_input
            for prefix in ["run", "execute"]:
                if user_lower.startswith(prefix):
                    cmd = user_input[len(prefix):].strip()
                    break
            return json.dumps({
                "thought": f"Run command: {cmd}",
                "action": "run_command",
                "args": {"command": cmd},
                "response": None
            })

        return json.dumps({
            "thought": "Direct response",
            "action": None,
            "args": {},
            "response": f"[FakeLLM] I understood: '{user_input}'"
        })


class OllamaLLM(LLMInterface):
    """Ollama LLM implementation for local models."""

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip('/')
        self._check_ollama()

    @property
    def name(self) -> str:
        return f"Ollama ({self.model})"

    def _check_ollama(self):
        """Verify Ollama is available."""
        try:
            import requests
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code != 200:
                raise ConnectionError(f"Ollama returned status {response.status_code}")
        except ImportError:
            raise ImportError("requests package required for Ollama")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Ollama: {e}")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Ollama API."""
        import requests

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.7}
        }

        response = requests.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=120
        )
        response.raise_for_status()

        result = response.json()
        return result["message"]["content"]


class AnthropicLLM(LLMInterface):
    """Anthropic Claude API implementation."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model

        if not api_key:
            import os
            self.api_key = os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY.")

    @property
    def name(self) -> str:
        return f"Anthropic ({self.model})"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Anthropic API."""
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("anthropic package required")

        client = Anthropic(api_key=self.api_key)

        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return response.content[0].text


class LLMFactory:
    """Factory for creating LLM instances."""

    @staticmethod
    def create(provider: str, **kwargs) -> LLMInterface:
        """
        Create an LLM instance based on provider name.

        Args:
            provider: 'fake', 'deterministic', 'ollama', or 'anthropic'
            **kwargs: Provider-specific arguments

        Returns:
            LLMInterface instance
        """
        providers = {
            "fake": FakeLLM,
            "deterministic": DeterministicLLM,
            "ollama": OllamaLLM,
            "anthropic": AnthropicLLM,
        }

        if provider not in providers:
            raise ValueError(f"Unknown provider: {provider}. Available: {list(providers.keys())}")

        return providers[provider](**kwargs)
