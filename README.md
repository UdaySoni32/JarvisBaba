# Jarvis - Autonomous AI Agent Runtime

A comprehensive AI agent runtime system built in Python with persistent task management, intelligent scheduling, and autonomous decision-making capabilities.

## 🎯 Overview

Jarvis is a sophisticated multi-step planning agent that goes beyond simple LLM interactions. It can:

- **Execute multi-step plans** with state tracking and reflection
- **Manage persistent tasks** that survive restarts
- **Schedule delayed and recurring tasks** with natural language support
- **React to events** through a pub/sub event system
- **Make autonomous decisions** based on system context
- **Validate and sandbox tool execution** for safety
- **Log everything** with structured JSONL execution traces

## ✨ Key Features

### Phase 1: Persistent Task Management
- ✅ Task creation, persistence, and lifecycle management
- ✅ Background execution (fire-and-forget) and foreground execution (waits for completion)
- ✅ Task status tracking (pending → running → completed/failed)
- ✅ Automatic retry logic with exponential backoff
- ✅ Atomic file storage with integrity checks

### Phase 2: Task Scheduling & Event-Driven Execution
- ✅ **Delayed scheduling** - "remind me in 10 minutes"
- ✅ **Recurring tasks** - "run this every hour"
- ✅ **Event-triggered execution** - "do X when Y happens"
- ✅ **Natural language parsing** - understands human-friendly timing expressions
- ✅ **Priority-based fair dispatch** - prevents task starvation
- ✅ **Event bus** - centralized pub/sub for system events

### Phase 3: Autonomous Decision-Making
- ✅ **Context aggregation** - monitors events, task history, failures, patterns
- ✅ **Intelligent decision engine** - uses heuristics + optional LLM scoring
- ✅ **Autonomous background loop** - periodically evaluates and acts
- ✅ **Safety guardrails**:
  - Rate limiting (max 5 tasks per hour)
  - Task deduplication (prevents redundant tasks)
  - Confidence thresholds (only acts when confident)
  - Conservative defaults (autonomy disabled by default)
- ✅ **Full transparency** - all decisions logged with reasoning

## 🏗️ Architecture

```
User Input / Commands
        ↓
    ┌───┴───────────────────┐
    │                       │
    ▼                       ▼
Foreground               Background / Autonomy
Execution                 Execution
    │                       │
    │              ┌────────┴───────────┐
    │              ▼                    ▼
    │         TaskManager         AutonomousLoop
    │              │                    │
    └──────┬───────┘                    │
           │                  ContextAggregator
           │                            │
           │                  DecisionEngine
           │                            │
    ┌──────▼────────────────────────────┤
    │                                   ▼
    │    Planner → Executor → Reflection
    │        (Multi-step planning)
    │
    ├─ Scheduler (delayed/recurring tasks)
    ├─ EventBus (event-driven execution)
    ├─ ToolValidator (safety & sandboxing)
    ├─ ExecutionLogger (JSONL traces)
    └─ Memory (execution state)
```

## 📦 Project Structure

```
jarvis/
├── core/
│   ├── agent.py              # LLM-based decision making
│   ├── planner.py            # Multi-step plan generation
│   ├── executor.py           # Validated tool execution
│   ├── reflection.py         # Step evaluation & next action
│   ├── state.py              # Execution state machine
│   ├── validator.py          # Tool validation & safety
│   ├── logging.py            # Structured JSONL logging
│   ├── scheduler.py          # Task scheduling
│   ├── schedule_parser.py    # NLP schedule parsing
│   ├── context_aggregator.py # System state collection
│   ├── decision_engine.py    # Autonomous decision logic
│   ├── autonomous_loop.py    # Background autonomy loop
│   ├── tasks/
│   │   ├── task.py           # Task model
│   │   └── task_manager.py   # Task lifecycle & persistence
│   ├── events/
│   │   └── event_bus.py      # Event pub/sub system
│   ├── tools/
│   │   ├── terminal.py       # Command execution
│   │   ├── apps.py           # App launching
│   │   └── schema.py         # Tool definitions
│   └── memory/
│       └── short_term.py     # Execution memory
├── models/
│   └── llm.py                # LLM abstraction (OpenAI, Claude, Ollama, etc)
├── interface/
│   └── tui.py                # Terminal user interface
├── tests/                    # Comprehensive test suite (50+ tests)
├── data/
│   └── tasks.json            # Persistent task storage
├── logs/
│   └── execution.jsonl       # Execution traces
├── main.py                   # Entry point
├── requirements.txt          # Dependencies
├── AUTONOMY_SYSTEM.md        # Autonomy documentation
└── TASK_SCHEDULING_GUIDE.md  # Scheduling documentation
```

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/UdaySoni32/JarvisBaba.git
cd JarvisBaba

# Create virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Start the Jarvis interactive shell
python3 main.py
```

**Available Commands:**

```
Task Management:
  list tasks              - Show all tasks
  pause task <id>         - Pause a task
  resume task <id>        - Resume a task
  cancel task <id>        - Cancel a task

Scheduling:
  list scheduled          - Show scheduled tasks
  list events             - Show event listeners
  trigger <event>         - Fire an event

Autonomy:
  enable autonomy         - Start autonomous mode
  disable autonomy        - Stop autonomous mode
  autonomy status         - Show autonomy status

General:
  help                    - Show all commands
  clear                   - Clear screen
  logs                    - Show recent logs
  quit/exit               - Exit the program
```

### Examples

#### Create a Task
```
User: "Create a task to review the quarterly report"
Jarvis: Task created with ID: task-abc123
```

#### Schedule a Task
```
User: "Remind me to check the logs in 10 minutes"
Jarvis: Scheduled task to run in 10 minutes
```

#### Recurring Task
```
User: "Run system diagnostics every hour"
Jarvis: Created recurring task (interval: 3600 seconds)
```

#### Event-Driven Task
```
User: "Alert me when the backup completes"
Jarvis: Task will trigger when 'backup_completed' event fires
```

#### Enable Autonomy
```
> enable autonomy
Autonomous mode enabled

[System monitoring...]
Detected: high failure rate
Creating diagnostic task: "investigate system health"
```

## 🧠 Decision Heuristics

The autonomous decision engine uses these heuristics:

1. **Failure Investigation**
   - When: Recent failed tasks detected
   - Action: Propose diagnostic task
   - Confidence: 0.8

2. **High Failure Rate**
   - When: >20% of recent tasks failed
   - Action: Propose system health check
   - Confidence: 0.7

3. **Normal Operation**
   - When: No issues detected
   - Action: No action needed
   - Confidence: 0.95

Optional LLM-based scoring for nuanced edge cases.

## 🔒 Safety & Validation

Jarvis includes multiple layers of safety:

### Tool Validation
- Blocks dangerous commands (rm -rf, shutdown, etc)
- Sandboxes tool execution
- Validates arguments before execution

### Autonomy Guardrails
- **Rate Limiting**: Max 5 autonomous tasks/hour
- **Deduplication**: Prevents creating duplicate tasks
- **Confidence Thresholds**: Only acts on high-confidence decisions
- **Conservative Defaults**: Autonomy disabled by default
- **Full Audit Trail**: Every decision logged with reasoning

### Execution Safety
- State machine prevents invalid transitions
- Automatic retry with backoff (up to 3 times)
- Graceful error handling and recovery
- Thread-safe concurrent operations

## 📊 Logging & Observability

All execution is logged to `logs/execution.jsonl`:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "type": "task_created",
  "task_id": "task-abc123",
  "goal": "review quarterly report",
  "mode": "background",
  "priority": 5
}
```

Autonomy decisions logged with full reasoning:

```json
{
  "timestamp": "2024-01-15T10:31:00Z",
  "source": "autonomy",
  "decision": {
    "should_act": true,
    "reason": "Detected recent task failures; recommending diagnostics",
    "confidence": 0.82,
    "proposed_task": {
      "goal": "investigate system health",
      "priority": 7
    }
  }
}
```

## 🧪 Testing

Comprehensive test suite with 50+ test cases:

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_autonomy.py -v

# Run with coverage
python3 -m pytest tests/ --cov=core --cov=models
```

**Test Coverage:**
- ✅ Task persistence and lifecycle
- ✅ Scheduling (delayed, recurring)
- ✅ Event system and triggering
- ✅ Autonomous decision making
- ✅ Rate limiting and deduplication
- ✅ Thread safety and concurrency
- ✅ Tool validation and execution
- ✅ Logging and traces

## 📚 Documentation

- **[AUTONOMY_SYSTEM.md](AUTONOMY_SYSTEM.md)** - Complete autonomy guide with architecture, heuristics, and guardrails
- **[TASK_SCHEDULING_GUIDE.md](TASK_SCHEDULING_GUIDE.md)** - Task scheduling and event system documentation
- Inline code documentation with type hints and docstrings

## ⚙️ Configuration

### Environment Variables

```bash
# Autonomy settings
JARVIS_AUTONOMY=true                  # Enable autonomy at startup
JARVIS_AUTONOMY_RATE_LIMIT=5          # Max autonomous tasks per hour
JARVIS_AUTONOMY_CONFIDENCE=0.7        # Decision confidence threshold
JARVIS_AUTONOMY_POLL_INTERVAL=30      # Polling interval in seconds
JARVIS_AUTONOMY_MAX_CONCURRENT=2      # Max concurrent autonomous tasks

# LLM settings
JARVIS_LLM_PROVIDER=ollama            # Provider: ollama, openai, claude, anthropic
JARVIS_LLM_MODEL=llama3.2             # Model name
```

### LLM Configuration

Jarvis supports multiple LLM providers:

```python
from models.llm import LLMFactory

# Using Ollama (local)
llm = LLMFactory.create("ollama", model="llama3.2")

# Using OpenAI
llm = LLMFactory.create("openai", api_key="sk-...")

# Using Anthropic Claude
llm = LLMFactory.create("anthropic", api_key="sk-ant-...")

# Deterministic LLM (for testing)
llm = LLMFactory.create("deterministic")
```

## 🔄 Data Persistence

### Tasks Storage
```
data/tasks.json
```
- Atomic writes prevent corruption
- Auto-loaded on startup
- Survives crashes/restarts

### Execution Logs
```
logs/execution.jsonl
```
- Structured JSON format
- Full execution traces
- Searchable and analyzable
- Autonomous decisions logged with reasoning

## 🎓 Learn More

### System Architecture
The system follows a modular, clean architecture:
- **Agent** - LLM-based decision classification
- **Planner** - Multi-step plan generation
- **Executor** - Validated tool execution
- **Reflector** - Step evaluation and next action determination
- **TaskManager** - Task lifecycle and persistence
- **Scheduler** - Delayed/recurring task scheduling
- **EventBus** - Event pub/sub coordination
- **ContextAggregator** - System state collection
- **DecisionEngine** - Autonomous decision making
- **AutonomousLoop** - Background evaluation thread

### Multi-Step Planning Example

```python
# User input
"Review quarterly report and send summary to team"

# Planner generates steps
1. Open quarterly report file
2. Read and analyze report
3. Summarize key findings
4. Draft email message
5. Send email to team members

# Executor runs each step with validation
# Reflector evaluates success and decides next action
# If step fails → retry with backoff
# If successful → continue to next step
# If final step succeeds → task marked completed
```

### Task Lifecycle

```
pending → running → completed
             ↓
          (if failed)
             ↓
          retry  → running (up to 3 times)
             ↓
          (max retries exceeded)
             ↓
          failed

# For recurring tasks
completed → pending (reschedule with interval)
```

## 🚧 Known Limitations

- Single-server only (no distributed scheduling)
- Internal EventBus only (no external webhooks)
- Basic string similarity for deduplication (no embeddings)
- Heuristics tuned for general use (may need domain adjustment)

## 🎯 Future Enhancements

- [ ] Separate autonomy.jsonl log file
- [ ] Metrics dashboard (decisions, success rate)
- [ ] Learning loop (improve heuristics over time)
- [ ] External event triggers (webhooks)
- [ ] Cost/resource estimation
- [ ] User feedback integration
- [ ] Advanced pattern detection
- [ ] Distributed task scheduling
- [ ] Web API for remote interaction
- [ ] Domain-specific heuristics

## 📄 License

[Add your license information here]

## 👤 Author

Created by Uday Soni

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📞 Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing documentation
- Review test cases for usage examples

## 🎉 Acknowledgments

Built as a comprehensive upgrade to the Jarvis AI agent system, supporting persistent task management, intelligent scheduling, and autonomous decision-making.

---

**Status**: ✅ Production-Ready
**Version**: 1.0.0
**Last Updated**: January 2024
