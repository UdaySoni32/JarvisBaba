# Jarvis Autonomous Decision-Making System

## Overview

The Autonomous Decision-Making System transforms Jarvis from a reactive agent into a proactive system that can observe context, evaluate opportunities, and autonomously create tasks without user input.

**Design Philosophy**: Safety > Intelligence
- Conservative defaults (autonomy disabled by default)
- All actions must pass through existing TaskManager
- Multiple layers of guardrails to prevent spam/loops
- Explainable decisions with full reasoning logs

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│         User Commands                           │
│  (enable autonomy, disable autonomy, etc)       │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │  AutonomousLoop (Thread)│ runs every 30-60s
        └────────────┬────────────┘
                     │
        ┌────────────▼──────────────────┐
        │  ContextAggregator            │
        │  Collects system state        │
        │  - events                     │
        │  - task history               │
        │  - failures                   │
        │  - patterns                   │
        └────────────┬──────────────────┘
                     │
        ┌────────────▼──────────────────┐
        │  DecisionEngine               │
        │  Evaluates context            │
        │  - Heuristics (fast)          │
        │  - LLM scoring (optional)     │
        └────────────┬──────────────────┘
                     │
        ┌────────────▼────────────────────────┐
        │  Guardrails & Checks                │
        │  - Rate limiting (max/hour)         │
        │  - Deduplication                    │
        │  - Confidence threshold             │
        └────────────┬────────────────────────┘
                     │
        ┌────────────▼──────────────────┐
        │  TaskManager                  │
        │  (Create & Queue Task)        │
        └────────────┬──────────────────┘
                     │
        ┌────────────▼──────────────────┐
        │  ExecutionLogger              │
        │  (Log autonomy decision)      │
        └──────────────────────────────┘
```

---

## Components

### 1. ContextAggregator (`core/context_aggregator.py`)

Collects real-time system state for decision-making.

**Inputs:**
- TaskManager (pending, running, completed, failed tasks)
- EventBus (recent events from the system)

**Outputs:**
```python
{
    "timestamp": "2024-01-15T10:30:00Z",
    "recent_events": [
        {"name": "task_completed", "count": 3, "timestamp": "..."},
        {"name": "task_failed", "count": 1, "timestamp": "..."}
    ],
    "task_summary": {
        "pending": 2,
        "running": 1,
        "completed": 15,
        "failed": 1,
        "paused": 0
    },
    "failed_tasks": [
        {
            "id": "task-123",
            "goal": "check system logs",
            "failure_reason": "connection timeout"
        }
    ],
    "active_tasks": [
        {
            "id": "task-456",
            "goal": "backup database",
            "status": "running"
        }
    ],
    "recurring_patterns": {
        "recurring_task_count": 3,
        "failed_task_count": 1,
        "completed_task_count": 15,
        "has_failures": True,
        "high_completion_rate": True
    }
}
```

**Key Methods:**
- `get_context()` - Full system context snapshot
- `get_autonomy_state()` - For TUI display

---

### 2. DecisionEngine (`core/decision_engine.py`)

Evaluates context and decides whether to create a new task.

**Decision Heuristics (evaluated in order):**

1. **Failure Investigation** - If recent failed tasks exist
   - Propose diagnostic task (e.g., "investigate failed task X")
   - Confidence: 0.8

2. **High Failure Rate** - If >20% of recent tasks failed
   - Propose system health check
   - Confidence: 0.7

3. **Normal Operation** - If no issues detected
   - Confidence: 0.95
   - No action needed

**Optional LLM Scoring:**
- If heuristics don't match, can use LLM for nuanced evaluation
- Requires OpenAI/Claude/Ollama configured
- LLM gets context and returns JSON decision

**Output:**
```python
AutonomousDecision(
    should_act=True,
    reason="Detected recent task failures; recommending diagnostic",
    confidence=0.82,
    proposed_task={
        "goal": "investigate system health",
        "priority": 7,
        "mode": "background"
    }
)
```

**Confidence Threshold:** 0.7 (configurable)
- Decisions below threshold are logged but not acted upon
- Prevents risky autonomous actions

---

### 3. AutonomousLoop (`core/autonomous_loop.py`)

Background thread that periodically evaluates opportunities and creates tasks.

**Execution Flow:**
1. Poll every N seconds (default 30)
2. Get context from ContextAggregator
3. Call DecisionEngine.decide()
4. Check guardrails:
   - Rate limiting (max tasks/hour)
   - Deduplication (avoid creating duplicate tasks)
   - Confidence threshold
5. If all pass: create task via TaskManager
6. Log decision with reasoning

**Configuration:**
```python
loop = AutonomousLoop(
    engine=decision_engine,
    task_manager=task_manager,
    poll_interval=30,              # seconds
    max_tasks_per_hour=5,          # rate limit
    max_concurrent_autonomous=2,   # prevent overload
    similarity_threshold=0.7       # for deduplication
)
```

---

## Guardrails

### 1. Rate Limiting
- **Max N tasks per hour** (default: 5)
- Sliding window: counts tasks created in last 3600 seconds
- Prevents task spam

```python
if self._count_recent_autonomous_tasks() >= self.max_tasks_per_hour:
    return  # Skip creation
```

### 2. Task Deduplication
- Before creating task, check for similar tasks in pending/running
- Uses string similarity: Jaccard distance on words
- Similarity threshold: 0.7 (configurable)

```python
existing = task_manager.list_tasks(
    filters={"status": ["pending", "running"]}
)
for task in existing:
    if self._goal_similarity(
        new_goal,
        task.goal
    ) > threshold:
        return  # Skip - duplicate detected
```

### 3. Confidence Threshold
- Only act on decisions with confidence >= 0.7
- Heuristics typically return 0.7-0.95
- LLM decisions filtered to exclude marginal cases

---

## Integration Points

### Agent Integration
```python
agent.enable_autonomy()   # Start autonomous decision-making
agent.disable_autonomy()  # Pause autonomy
agent.is_autonomy_enabled()  # Check status
```

### Commands
```
enable autonomy    → Start autonomous mode
disable autonomy   → Stop autonomous mode
autonomy status    → Show recent decisions and status
```

### TUI Display
```
[Autonomous Status]
Status: ENABLED
Recent Decisions:
  [ACTED] High failure rate detected (confidence=0.82)
  [WAIT] System healthy, no action needed (confidence=0.95)
  [SKIP] Low confidence decision, ignored (confidence=0.45)
```

---

## Logging

All autonomous decisions logged in:
- `logs/execution.jsonl` (with `"source": "autonomy"`)

**Decision Log Format:**
```json
{
    "timestamp": "2024-01-15T10:30:45Z",
    "source": "autonomy",
    "decision": {
        "should_act": true,
        "reason": "Detected recent task failures; recommending diagnostics",
        "confidence": 0.82,
        "proposed_task": {
            "goal": "investigate system health",
            "priority": 7,
            "mode": "background"
        }
    },
    "guardrails": {
        "passed_rate_limit": true,
        "passed_deduplication": true,
        "passed_confidence": true
    }
}
```

---

## Safety Defaults

1. **Autonomy disabled by default**
   - User must explicitly enable: `enable autonomy`
   - Conservative approach ensures no surprise actions

2. **Heuristic-first approach**
   - LLM scoring optional
   - Heuristics are deterministic and tested

3. **Rate limiting**
   - Max 5 tasks/hour prevents runaway
   - Configurable per deployment

4. **Deduplication**
   - Prevents infinite loops
   - Detects similar goals

5. **Confidence thresholds**
   - Only act on high-confidence decisions
   - Marginal calls are logged but skipped

6. **Explainability**
   - Every decision logged with full reasoning
   - Users can review autonomy history and understand why actions were taken

---

## Example Scenarios

### Scenario 1: Failure Detection
```
1. Task "backup database" fails
2. ContextAggregator detects failure in recent_events
3. DecisionEngine heuristic triggers: "failure investigation"
4. Autonomy checks: rate_limit ✓, dedup ✓, confidence ✓
5. Creates task: "investigate backup failure"
6. Log: decision + reasoning + guardrails passed
```

### Scenario 2: Duplicate Prevention
```
1. User created task: "check system logs"
2. Autonomy considers creating similar task: "check logs for errors"
3. Deduplication check: similarity = 0.85 > 0.7
4. Skip creation (would be duplicate)
5. Log: decision + reason "duplicate detected"
```

### Scenario 3: Low Confidence Filtered
```
1. LLM scorer returns: confidence=0.55, should_act=true
2. Threshold check: 0.55 < 0.7
3. Skip action but log decision
4. User can review in logs if interested
```

---

## Performance & Thread Safety

**Thread Safety:**
- ContextAggregator uses RLock for task dict access
- DecisionEngine is stateless (thread-safe)
- AutonomousLoop uses event-based coordination
- TaskManager already thread-safe

**Performance:**
- ContextAggregator: O(N) tasks - fast, doesn't lock for long
- DecisionEngine: O(1) heuristics, LLM call optional
- AutonomousLoop: polls every 30s (configurable), minimal overhead
- Deduplication: O(M) similar task check - fast for typical task counts

**Resource Usage:**
- One daemon thread for autonomy loop
- Low CPU: idle between poll intervals
- Memory: decision history limited to 100 entries

---

## Configuration (Environment Variables)

```bash
# Enable autonomy at startup (default: false)
JARVIS_AUTONOMY=true

# Decision engine LLM provider (optional)
JARVIS_LLM_PROVIDER=openai

# Autonomy rate limit (tasks per hour)
JARVIS_AUTONOMY_RATE_LIMIT=5

# Confidence threshold for autonomous actions
JARVIS_AUTONOMY_CONFIDENCE=0.7

# Autonomy poll interval (seconds)
JARVIS_AUTONOMY_POLL_INTERVAL=30

# Max concurrent autonomous tasks
JARVIS_AUTONOMY_MAX_CONCURRENT=2
```

---

## Testing

**Autonomy Test Suite** (`tests/test_autonomy.py`):
- Context aggregation
- Decision heuristics
- Failure detection
- Loop start/stop
- Rate limiting
- Deduplication
- Enable/disable toggle
- Decision callback
- Decision history

Run tests:
```bash
python3 -m pytest tests/test_autonomy.py -v
```

---

## Future Enhancements

1. **Separate autonomy.jsonl** - Dedicated log file for autonomy
2. **Metrics** - Track decision quality, success rate
3. **Learning** - Improve heuristics based on outcomes
4. **Webhooks** - React to external events
5. **Advanced patterns** - Detect complex recurring issues
6. **Cost estimation** - Autonomous actions with resource awareness
7. **User feedback loop** - Learn from user corrections

---

## Troubleshooting

**Autonomy not triggering:**
- Check: `autonomy status` command
- Verify: JARVIS_AUTONOMY env var or `enable autonomy` command
- Check logs: `/logs/execution.jsonl` for decision history

**Too many autonomous tasks:**
- Reduce `max_tasks_per_hour` (lower limit)
- Increase `confidence_threshold` (stricter filter)
- Check: deduplication logic catching duplicates?

**Duplicate tasks being created:**
- Check similarity threshold (currently 0.7)
- Review task goals for similarity
- May need to adjust heuristics

**Decision engine crashes:**
- Check logs for error messages
- If LLM scoring enabled, verify API connectivity
- Fall back to heuristics-only mode

---

## Architecture Decisions

### Why heuristics-first?
- Deterministic behavior
- No API latency (offline-capable)
- Testable and debuggable
- Safe by default

### Why rate limiting?
- Prevents task spam
- Prevents resource exhaustion
- Prevents infinite loops

### Why deduplication?
- Avoids creating redundant tasks
- Prevents user confusion
- Reduces system load

### Why daemon threads?
- Doesn't block program exit
- Loop stops cleanly on shutdown
- No hanging processes

### Why separate ContextAggregator?
- Single responsibility
- Reusable for other components
- Testable in isolation

---

## References

See also:
- `/core/context_aggregator.py` - Context collection
- `/core/decision_engine.py` - Decision logic
- `/core/autonomous_loop.py` - Execution loop
- `/core/agent.py` - Agent autonomy control
- `/core/logging.py` - Autonomy logging
- `/tests/test_autonomy.py` - Test suite
