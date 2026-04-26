"""
Pytest configuration and shared fixtures.
"""
import pytest
import tempfile
import shutil
from pathlib import Path

from models.llm import DeterministicLLM, FakeLLM
from core.agent import Agent
from core.planner import Planner
from core.executor import Executor
from core.reflection import Reflector
from core.memory.short_term import ShortTermMemory
from core.logging import ExecutionLogger


@pytest.fixture
def temp_log_dir():
    """Provide temporary log directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def deterministic_llm():
    """Provide deterministic LLM for reproducible tests."""
    return DeterministicLLM(seed=42)


@pytest.fixture
def fake_llm():
    """Provide fake LLM."""
    return FakeLLM()


@pytest.fixture
def noop_llm():
    """Provide no-op LLM for minimal execution."""
    return DeterministicLLM(noop=True)


@pytest.fixture
def memory():
    """Provide fresh short-term memory."""
    return ShortTermMemory(max_messages=10)


@pytest.fixture
def executor():
    """Provide executor with tools registered."""
    from core.tools.terminal import run_command
    from core.tools.apps import open_app

    exec = Executor()
    exec.register_tool("run_command", run_command)
    exec.register_tool("open_app", open_app)
    return exec


@pytest.fixture
def strict_executor():
    """Provide strict mode executor."""
    from core.tools.terminal import run_command

    exec = Executor(strict_mode=True)
    exec.register_tool("run_command", run_command)
    return exec


@pytest.fixture
def planner(fake_llm):
    """Provide planner with fake LLM."""
    return Planner(fake_llm)


@pytest.fixture
def deterministic_planner(deterministic_llm):
    """Provide planner with deterministic LLM."""
    return Planner(deterministic_llm)


@pytest.fixture
def agent(fake_llm, memory, executor):
    """Provide agent with fake LLM."""
    return Agent(fake_llm, memory, executor.get_available_tools())


@pytest.fixture
def reflector(fake_llm):
    """Provide reflector with fake LLM."""
    return Reflector(fake_llm)


@pytest.fixture
def logger(temp_log_dir):
    """Provide execution logger with temp directory."""
    return ExecutionLogger(log_dir=temp_log_dir)


@pytest.fixture
def debug_logger(temp_log_dir):
    """Provide execution logger in debug mode."""
    return ExecutionLogger(log_dir=temp_log_dir, debug_mode=True)
