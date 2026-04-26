"""Task-routing tests for Agent."""

from core.agent import Agent
from core.memory.short_term import ShortTermMemory
from models.llm import FakeLLM


def test_background_task_intent_detection():
    agent = Agent(FakeLLM(), ShortTermMemory(), [])
    decision = agent.classify_task_intent("Run backup in background and notify me later")
    assert decision.should_create_task is True
    assert decision.mode == "background"


def test_simple_input_not_forced_into_task():
    agent = Agent(FakeLLM(), ShortTermMemory(), [])
    decision = agent.classify_task_intent("hello")
    assert decision.should_create_task is False
