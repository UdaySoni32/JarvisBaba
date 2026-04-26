#!/usr/bin/env python3
"""
Jarvis - Robust Multi-Step Planning Agent System
Main entry point with state machine, validation, and safety controls.

Architecture:
    User Input → Mode Classifier → [Single | Multi] Execution

    Multi-step flow:
    Planner → ExecutionState → Validate → Execute → Reflect → [Continue|Retry|Replan|Stop]

Modules:
    - core/agent.py: Mode classification and single-turn decisions
    - core/planner.py: Multi-step plan generation
    - core/executor.py: Validated tool execution
    - core/reflection.py: Step evaluation with NextAction
    - core/state.py: Formal execution state machine
    - core/validator.py: Tool validation and safety
    - core/logging.py: Structured execution logging
    - core/memory: Execution state tracking
    - core/tools: System interaction tools
    - models/llm.py: LLM abstraction
    - interface/tui.py: Terminal user interface
"""
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.llm import LLMFactory
from core.agent import Agent
from core.planner import Planner
from core.executor import Executor
from core.reflection import Reflector, NextAction
from core.state import ExecutionState, StepState, ExecutionMode, StepStatus
from core.memory.short_term import ShortTermMemory
from core.tools.terminal import run_command
from core.tools.apps import open_app
from core.tools.schema import get_tool_schemas
from core.validator import ToolValidator
from core.logging import ExecutionLogger
from core.tasks.task_manager import TaskManager
from core.goals.goal_manager import GoalManager
from core.alignment import AlignmentLayer
from core.learning import PatternMemory, FeedbackCollector
from core.scheduler import Scheduler
from core.events import EventBus
from core.context_aggregator import ContextAggregator
from core.decision_engine import DecisionEngine
from core.autonomous_loop import AutonomousLoop
from interface.tui import TUI


def setup_executor(strict_mode: bool = False) -> Executor:
    """Create executor with validation and tools."""
    executor = Executor(strict_mode=strict_mode)
    executor.register_tool("run_command", run_command)
    executor.register_tool("open_app", open_app)
    return executor


def create_system(llm_provider: str = "fake", strict_mode: bool = False):
    """Initialize the complete agent system.

    Returns:
        Tuple of (Agent, Planner, Executor, Reflector, Memory, Logger, LLM)
    """
    llm = LLMFactory.create(llm_provider)
    memory = ShortTermMemory(max_messages=20)
    executor = setup_executor(strict_mode)
    logger = ExecutionLogger()

    planner = Planner(llm)
    agent = Agent(llm, memory, executor.get_available_tools())
    reflector = Reflector(llm)

    return agent, planner, executor, reflector, memory, logger, llm


def execute_single_turn(
    user_input: str,
    agent: Agent,
    executor: Executor,
    tui: TUI,
    memory: ShortTermMemory,
    logger: ExecutionLogger
) -> str:
    """Handle single-turn execution with validation."""
    decision = agent.decide(user_input)
    tui.print_thought(decision.thought)

    if decision.requires_tool:
        tui.print_action(decision.action, decision.args)
        result = executor.execute(decision)
        tui.print_tool_output(result.to_dict())

        # Log
        logger.log_step_result(
            step_id=0,
            success=result.success,
            result=result.result,
            error=result.message if not result.success else None
        )

        if result.validation and result.validation.blocked:
            response_text = f"BLOCKED: {result.validation.block_reason}"
        elif result.success:
            output = result.result
            if isinstance(output, dict) and "stdout" in output:
                response_text = f"Done!\n\nOutput:\n{output['stdout']}"
            else:
                response_text = f"Done! {result.message}"
        else:
            response_text = f"Failed: {result.message}"

        tui.print_response(response_text)
        memory.add_message("assistant", response_text)
    else:
        response = decision.response or "I have nothing to say."
        tui.print_response(response)
        memory.add_message("assistant", response)

    return decision.response or ""


def execute_multi_step_plan(
    goal: str,
    planner: Planner,
    executor: Executor,
    reflector: Reflector,
    tui: TUI,
    memory: ShortTermMemory,
    logger: ExecutionLogger,
    task_id: str = None,
    task_manager: TaskManager = None,
    quiet: bool = False,
) -> bool:
    """Execute multi-step plan with state machine and recovery.

    Returns True if completed successfully.
    """
    def _emit(method: str, *args):
        if quiet:
            return
        if hasattr(tui, method):
            getattr(tui, method)(*args)

    # Generate plan
    _emit("print_system_message", "Analyzing and planning...", "info")
    plan = planner.create_plan(goal)

    if not plan.steps:
        _emit("print_system_message", "Could not create a plan for this goal", "error")
        logger.log_error("planning", "No steps generated for goal", {"goal": goal}, task_id=task_id)
        if task_id and task_manager:
            task_manager.mark_task_failed(task_id, "No steps generated")
        return False

    # Create execution state
    step_states = [
        StepState(
            id=s.id,
            action=s.action,
            args=s.args,
            max_attempts=3
        )
        for s in plan.steps
    ]
    state = ExecutionState(goal=plan.goal, steps=step_states, mode=ExecutionMode.MULTI_STEP)
    state.status = "running"

    # Log
    logger.log_plan(goal, plan.to_dict(), len(executor.get_available_tools()), task_id=task_id)
    if task_id and task_manager:
        task_manager.set_task_steps(task_id, [s.to_dict() for s in state.steps])

    # Display
    _emit("print_goal", state.goal)
    _emit("print_execution_state", state)

    replan_count = 0
    max_replans = 2

    # Execution loop
    while not state.is_complete and replan_count <= max_replans:
        if task_id and task_manager:
            external_task = task_manager.get_task(task_id)
            if not external_task:
                state.abort("Task missing from manager")
                break
            if external_task.status == "paused":
                state.abort("Task paused")
                break
            if external_task.status == "failed":
                state.abort("Task cancelled")
                break

        current = state.current_step
        if not current:
            break

        # Validate before execution
        validator = ToolValidator()
        validation = validator.validate(current.action, current.args)

        if validation.blocked:
            current.block(validation.block_reason)
            current.validation_errors = [validation.block_reason]
            _emit("print_blocked_action", current.id, validation.block_reason)
            logger.log_validation(current.id, False, [], blocked=True, task_id=task_id)
            if task_id and task_manager:
                task_manager.set_task_steps(task_id, [s.to_dict() for s in state.steps])

            if not state.advance():
                break
            continue

        if not validation.is_valid:
            error_msg = "; ".join(validation.errors)
            current.block(error_msg)
            current.validation_errors = validation.errors
            _emit("print_validation_error", current.id, validation.errors)
            logger.log_validation(current.id, False, validation.errors, task_id=task_id)
            if task_id and task_manager:
                task_manager.set_task_steps(task_id, [s.to_dict() for s in state.steps])

            if not state.advance():
                break
            continue

        # Execute
        logger.log_step_start(current.id, current.action, current.args, current.attempts + 1, task_id=task_id)
        _emit("print_step_running", current.id, current.action, current.attempts + 1)
        if task_id and task_manager:
            task_manager.set_active_execution(task_id, {
                "step_id": current.id,
                "action": current.action,
                "attempt": current.attempts + 1
            })

        result = executor.execute_step(current)
        logger.log_step_result(current.id, result.success, result.result,
                              result.message if not result.success else None, task_id=task_id)
        if task_id and task_manager:
            task_manager.set_task_steps(task_id, [s.to_dict() for s in state.steps])

        # Reflect
        reflection = reflector.reflect(state, current, result.to_dict())
        logger.log_reflection(
            current.id,
            reflection.status.value,
            reflection.confidence,
            reflection.next_action.value,
            reflection.reasoning,
            task_id=task_id
        )

        _emit("print_reflection_result", reflection)

        # Handle reflection decision
        if reflection.next_action == NextAction.STOP:
            state.abort(reflection.reasoning)
            _emit("print_step_complete", current.id, current.action, current.status.value,
                                   "Execution stopped")
            break

        elif reflection.next_action == NextAction.REPLAN:
            replan_count += 1
            if replan_count > max_replans:
                state.abort("Max replans exceeded")
                _emit("print_system_message", "Max replan attempts exceeded", "error")
                break

            _emit("print_system_message", "Replanning...", "warning")
            old_plan_data = state.to_dict()
            plan = planner.replan(plan, reflection.reasoning)

            # Rebuild state with new plan
            step_states = [
                StepState(
                    id=s.id,
                    action=s.action,
                    args=s.args,
                    max_attempts=3
                )
                for s in plan.steps
            ]
            state = ExecutionState(goal=plan.goal, steps=step_states, mode=ExecutionMode.MULTI_STEP)
            state.status = "running"
            logger.log_replan(old_plan_data, state.to_dict(), reflection.reasoning, task_id=task_id)
            _emit("print_execution_state", state)
            if task_id and task_manager:
                task_manager.set_task_steps(task_id, [s.to_dict() for s in state.steps])
            continue

        elif reflection.next_action == NextAction.RETRY:
            if current.can_retry():
                _emit("print_system_message",
                    f"Retrying step {current.id} (attempt {current.attempts + 1})",
                    "warning")
                continue
            else:
                _emit("print_system_message",
                    f"Step {current.id} failed after {current.attempts} attempts",
                    "error")

        # Step complete - display result
        _emit("print_step_complete",
            current.id,
            current.action,
            current.status.value,
            result.message
        )

        # Advance or complete
        if reflection.next_action != NextAction.RETRY:
            if not state.advance():
                break

    # Completion
    completed = len(state.completed_steps)
    failed = len(state.failed_steps)
    blocked_count = len([s for s in state.steps if s.status == StepStatus.BLOCKED])
    total = len(state.steps)

    logger.log_completion(
        state.status,
        completed,
        failed + blocked_count,
        total,
        task_id=task_id
    )
    if task_id and task_manager:
        task_snapshot = task_manager.get_task(task_id)
        if task_snapshot and task_snapshot.status == "paused":
            task_manager.clear_active_execution(task_id)
        elif state.has_blocked or (completed == 0 and total > 0):
            task_manager.mark_task_failed(task_id, "Execution blocked or failed")
        elif completed == total or completed > 0:
            task_manager.mark_task_completed(task_id)
        task_manager.clear_active_execution(task_id)

    _emit("print_execution_summary", completed, failed + blocked_count, total, blocked_count)

    # Final response
    if state.has_blocked:
        _emit("print_response", f"Execution blocked: Safety check prevented dangerous action.")
        return False
    elif completed == total:
        _emit("print_response", f"Execution complete! All {total} steps successful.")
        return True
    elif completed > 0:
        _emit("print_response", f"Partially completed: {completed}/{total} steps successful.")
        return True
    else:
        _emit("print_response", f"Execution failed: {failed} steps failed, {blocked_count} blocked.")
        return False


def main():
    """Main execution loop with mode classification."""
    LLM_PROVIDER = os.getenv("JARVIS_LLM", "fake")
    STRICT_MODE = os.getenv("JARVIS_STRICT", "false").lower() == "true"
    AUTONOMY_ENABLED = os.getenv("JARVIS_AUTONOMY", "false").lower() == "true"

    tui = TUI()
    task_manager = None
    scheduler = None
    event_bus = None
    autonomy_loop = None

    try:
        agent, planner, executor, reflector, memory, logger, llm = create_system(
            LLM_PROVIDER, STRICT_MODE
        )
        task_manager = TaskManager()
        event_bus = EventBus()
        scheduler = Scheduler(task_manager, event_bus, max_concurrent=2, poll_interval=1.0)
        goal_manager = GoalManager()
        alignment_layer = AlignmentLayer()
        pattern_memory = PatternMemory()
        feedback_collector = FeedbackCollector(pattern_memory)
        
        context_agg = ContextAggregator(task_manager, event_bus)
        decision_engine = DecisionEngine(
            context_agg,
            task_manager,
            goal_manager=goal_manager,
            alignment_layer=alignment_layer,
            pattern_memory=pattern_memory,
            llm=llm,
            confidence_threshold=0.7
        )
        autonomy_loop = AutonomousLoop(decision_engine, task_manager, poll_interval=60.0, max_tasks_per_hour=5)
        
        if AUTONOMY_ENABLED:
            agent.enable_autonomy()
    except Exception as e:
        tui.print_system_message(f"Failed to initialize: {e}", "error")
        sys.exit(1)

    def _background_task_runner(task):
        logger.log_task_event(task.id, "background_started", {"goal": task.goal})
        success = execute_multi_step_plan(
            task.goal,
            planner,
            executor,
            reflector,
            tui,
            memory,
            logger,
            task_id=task.id,
            task_manager=task_manager,
            quiet=True
        )
        outcome = task_manager.finalize_execution(task.id, success)
        logger.log_task_event(task.id, "background_finished", {"success": success, "outcome": outcome})
        return success

    def _task_executor_callback(task_id: str) -> bool:
        """Callback for scheduler to execute a task."""
        task = task_manager.get_task(task_id)
        if not task:
            return False
        return _background_task_runner(task)

    def _on_autonomy_decision(decision):
        """Callback when autonomy makes a decision."""
        logger.log_autonomy_decision(decision.to_dict())

    scheduler.start(_task_executor_callback)
    autonomy_loop.set_decision_callback(_on_autonomy_decision)
    autonomy_loop.start()

    tui.print_start_message(llm.name)
    tui.print_system_message(f"Logging to: {logger.get_log_path()}", "info")
    if STRICT_MODE:
        tui.print_system_message("Strict mode enabled - dangerous commands blocked", "warning")
    if agent.is_autonomy_enabled():
        tui.print_system_message("Autonomous mode enabled", "info")

    # Main loop
    while True:
        try:
            all_tasks = [task.to_dict() for task in task_manager.list_tasks()]
            active = task_manager.get_active_execution()
            if all_tasks:
                tui.print_tasks_panel(all_tasks, active)

            user_input = tui.get_input().strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                tui.print_system_message("Goodbye!", "info")
                break

            if user_input.lower() == "clear":
                tui.clear_screen()
                continue

            if user_input.lower() == "help":
                tui.print_help()
                continue

            if user_input.lower() == "logs":
                summary = logger.summary()
                tui.print_system_message(f"Session: {summary['session_id']}", "info")
                tui.print_system_message(f"Entries: {summary['total_entries']}", "info")
                tui.print_system_message(f"Errors: {len(summary['errors'])}", "info")
                continue

            if user_input.lower() == "list tasks":
                tasks = [task.to_dict() for task in task_manager.list_tasks()]
                tui.print_tasks_panel(tasks, task_manager.get_active_execution())
                continue

            if user_input.lower().startswith("list scheduled"):
                scheduled = scheduler.list_scheduled_tasks()
                if scheduled:
                    tui.print_system_message("[Scheduled Tasks]", "info")
                    for s in scheduled:
                        tui.print_system_message(
                            f"  {s['id'][:8]}: {s['goal'][:40]} | next: {s['next_run_at']} | "
                            f"interval: {s['interval_seconds']}s",
                            "info"
                        )
                else:
                    tui.print_system_message("No scheduled tasks", "info")
                continue

            if user_input.lower().startswith("list events"):
                event_map = scheduler.list_event_listeners()
                if event_map:
                    tui.print_system_message("[Event Listeners]", "info")
                    for event_name, task_ids in event_map.items():
                        tui.print_system_message(
                            f"  {event_name}: {len(task_ids)} task(s)",
                            "info"
                        )
                else:
                    tui.print_system_message("No event listeners", "info")
                continue

            trigger_match = re.match(r"^trigger\s+(.+)$", user_input.strip(), re.IGNORECASE)
            if trigger_match:
                event_name = trigger_match.group(1).lower().strip()
                try:
                    scheduler.fire_event(event_name)
                    tui.print_system_message(f"Event '{event_name}' triggered", "success")
                    logger.log_task_event("system", "event_triggered", {"event": event_name})
                except Exception as e:
                    tui.print_system_message(str(e), "error")
                continue

            if user_input.lower() == "enable autonomy":
                agent.enable_autonomy()
                autonomy_loop.enable()
                tui.print_system_message("Autonomous mode enabled", "success")
                logger.log_task_event("system", "autonomy_enabled")
                continue

            if user_input.lower() == "disable autonomy":
                agent.disable_autonomy()
                autonomy_loop.disable()
                tui.print_system_message("Autonomous mode disabled", "success")
                logger.log_task_event("system", "autonomy_disabled")
                continue

            if user_input.lower().startswith("autonomy status"):
                status = "enabled" if agent.is_autonomy_enabled() else "disabled"
                decisions = autonomy_loop.get_recent_decisions(limit=5)
                tui.print_system_message(f"Autonomy: {status}", "info")
                if decisions:
                    tui.print_system_message("Recent decisions:", "info")
                    for d in decisions:
                        action = "ACTED" if d.get("should_act") else "WAIT"
                        tui.print_system_message(
                            f"  [{action}] {d.get('reason')[:50]} (confidence={d.get('confidence'):.2f})",
                            "info"
                        )
                else:
                    tui.print_system_message("No decisions yet", "info")
                continue

            pause_match = re.match(r"^pause task\s+([a-zA-Z0-9-]+)$", user_input.strip(), re.IGNORECASE)
            if pause_match:
                task_id = pause_match.group(1)
                try:
                    paused = task_manager.pause_task(task_id)
                    if paused:
                        tui.print_system_message(f"Task {task_id} paused", "success")
                        logger.log_task_event(task_id, "paused")
                    else:
                        tui.print_system_message(f"Task {task_id} cannot be paused", "warning")
                except Exception as e:
                    tui.print_system_message(str(e), "error")
                continue

            resume_match = re.match(r"^resume task\s+([a-zA-Z0-9-]+)$", user_input.strip(), re.IGNORECASE)
            if resume_match:
                task_id = resume_match.group(1)
                try:
                    resumed = task_manager.resume_task(task_id)
                    if not resumed:
                        tui.print_system_message(f"Task {task_id} cannot be resumed", "warning")
                        continue

                    task = task_manager.get_task(task_id)
                    logger.log_task_event(task_id, "resumed")
                    if task and task.mode == "foreground":
                        task_manager.mark_task_running(task_id)
                        execute_multi_step_plan(
                            task.goal,
                            planner,
                            executor,
                            reflector,
                            tui,
                            memory,
                            logger,
                            task_id=task_id,
                            task_manager=task_manager
                        )
                    else:
                        tui.print_system_message(f"Task {task_id} resumed in queue", "success")
                except Exception as e:
                    tui.print_system_message(str(e), "error")
                continue

            cancel_match = re.match(r"^cancel task\s+([a-zA-Z0-9-]+)$", user_input.strip(), re.IGNORECASE)
            if cancel_match:
                task_id = cancel_match.group(1)
                try:
                    cancelled = task_manager.cancel_task(task_id)
                    if cancelled:
                        tui.print_system_message(f"Task {task_id} cancelled", "success")
                        logger.log_task_event(task_id, "cancelled")
                    else:
                        tui.print_system_message(f"Task {task_id} cannot be cancelled", "warning")
                except Exception as e:
                    tui.print_system_message(str(e), "error")
                continue

            # Goal management commands
            create_goal_match = re.match(r"^create goal:\s*(.+?)(?:\spriority\s(\d+))?$", user_input.strip(), re.IGNORECASE)
            if create_goal_match:
                description = create_goal_match.group(1).strip()
                priority = int(create_goal_match.group(2) or 5)
                try:
                    goal = goal_manager.create_goal(description, priority=priority)
                    tui.print_system_message(f"Goal created: {goal.id[:8]}... - {description}", "success")
                    logger.log_task_event("system", "goal_created", {"goal_id": goal.id, "description": description})
                except Exception as e:
                    tui.print_system_message(f"Error creating goal: {str(e)}", "error")
                continue

            if user_input.lower() == "list goals":
                goals = goal_manager.list_goals()
                if not goals:
                    tui.print_system_message("No goals", "info")
                else:
                    tui.print_system_message("Active Goals:", "info")
                    for goal in goals:
                        tui.print_system_message(
                            f"  [{goal.status}] {goal.id[:8]}... P{goal.priority}: {goal.description}",
                            "info"
                        )
                continue

            complete_goal_match = re.match(r"^complete goal\s+([a-zA-Z0-9-]+)$", user_input.strip(), re.IGNORECASE)
            if complete_goal_match:
                goal_id = complete_goal_match.group(1)
                try:
                    goal_manager.complete_goal(goal_id)
                    tui.print_system_message(f"Goal {goal_id[:8]}... completed", "success")
                    logger.log_task_event("system", "goal_completed", {"goal_id": goal_id})
                except Exception as e:
                    tui.print_system_message(f"Error completing goal: {str(e)}", "error")
                continue

            # Autonomy mode commands
            autonomy_mode_match = re.match(r"^autonomy\s+(off|suggest|assist|full)$", user_input.strip(), re.IGNORECASE)
            if autonomy_mode_match:
                new_mode = autonomy_mode_match.group(1).lower()
                if agent.set_autonomy_mode(new_mode):
                    if new_mode != "off":
                        autonomy_loop.enable()
                    else:
                        autonomy_loop.disable()
                    tui.print_system_message(f"Autonomy mode set to: {new_mode.upper()}", "success")
                    logger.log_task_event("system", "autonomy_mode_changed", {"mode": new_mode})
                else:
                    tui.print_system_message("Invalid autonomy mode", "error")
                continue

            if user_input.lower().startswith("autonomy status"):
                mode = agent.get_autonomy_mode()
                tui.print_system_message(f"Autonomy Mode: {mode.upper()}", "info")
                decisions = autonomy_loop.get_recent_decisions(limit=3)
                if decisions:
                    tui.print_system_message("Recent Decisions:", "info")
                    for d in decisions:
                        action = "✓ ACT" if d.get("should_act") else "✗ WAIT"
                        goal_id = d.get("goal_id", "N/A")
                        tui.print_system_message(
                            f"  {action} | Goal: {goal_id[:8] if goal_id else 'N/A'} | {d.get('reason')[:40]}",
                            "info"
                        )
                continue

            # Approval commands
            approve_match = re.match(r"^approve\s+([a-zA-Z0-9-]+)$", user_input.strip(), re.IGNORECASE)
            if approve_match:
                task_id = approve_match.group(1)
                try:
                    approved = task_manager.approve_task(task_id)
                    if approved:
                        tui.print_system_message(f"Task {task_id[:8]}... approved", "success")
                        logger.log_task_event(task_id, "approved")
                    else:
                        tui.print_system_message(f"Task {task_id} not in waiting_approval state", "warning")
                except Exception as e:
                    tui.print_system_message(f"Error approving task: {str(e)}", "error")
                continue

            reject_match = re.match(r"^reject\s+([a-zA-Z0-9-]+)(?:\s+(.+))?$", user_input.strip(), re.IGNORECASE)
            if reject_match:
                task_id = reject_match.group(1)
                reason = reject_match.group(2) or "User rejected"
                try:
                    rejected = task_manager.reject_task(task_id, reason)
                    if rejected:
                        tui.print_system_message(f"Task {task_id[:8]}... rejected", "success")
                        logger.log_task_event(task_id, "rejected", {"reason": reason})
                    else:
                        tui.print_system_message(f"Task {task_id} not in waiting_approval state", "warning")
                except Exception as e:
                    tui.print_system_message(f"Error rejecting task: {str(e)}", "error")
                continue

            # Show pending approvals
            if user_input.lower() in {"list approvals", "pending approvals"}:
                pending = task_manager.list_pending_approvals()
                if not pending:
                    tui.print_system_message("No pending approvals", "info")
                else:
                    tui.print_system_message(f"Pending Approvals ({len(pending)}):", "info")
                    for task in pending:
                        tui.print_system_message(
                            f"  {task.id[:8]}... | {task.goal[:40]} | {task.approval_reasoning or 'N/A'}",
                            "warning"
                        )
                continue

            tui.print_user_input(user_input)
            memory.add_message("user", user_input)

            # Classify execution mode
            mode_decision = agent.classify_mode(user_input)
            logger.log_input(user_input, mode_decision.mode.value, mode_decision.reasoning)

            tui.print_mode_classified(
                mode_decision.mode.value,
                mode_decision.reasoning,
                mode_decision.confidence
            )

            task_intent = agent.classify_task_intent(user_input)
            if not task_intent.should_create_task and mode_decision.mode == ExecutionMode.MULTI_STEP:
                task_intent.should_create_task = True
                task_intent.mode = "foreground"
                task_intent.reasoning = "Multi-step goals are persisted as tasks"
                task_intent.confidence = max(task_intent.confidence, 0.7)

            if task_intent.should_create_task:
                schedule, trigger = agent.classify_schedule_intent(user_input)
                
                task = task_manager.create_task(
                    goal=user_input,
                    mode=task_intent.mode,
                    schedule=schedule or {"type": "immediate", "run_at": None, "interval": None},
                    trigger=trigger
                )
                logger.log_task_event(task.id, "created", {
                    "goal": user_input,
                    "mode": task.mode,
                    "schedule": task.schedule,
                    "trigger": task.trigger,
                    "reasoning": task_intent.reasoning,
                    "confidence": task_intent.confidence
                })

                response_payload = {
                    "task_id": task.id,
                    "mode": task.mode,
                    "message": "Task created"
                }
                tui.print_response(json.dumps(response_payload))

                if task.mode == "foreground":
                    task_manager.mark_task_running(task.id)
                    execute_multi_step_plan(
                        user_input,
                        planner,
                        executor,
                        reflector,
                        tui,
                        memory,
                        logger,
                        task_id=task.id,
                        task_manager=task_manager
                    )

                tasks = [item.to_dict() for item in task_manager.list_tasks()]
                tui.print_tasks_panel(tasks, task_manager.get_active_execution())
                tui.print_separator()
                continue

            if mode_decision.mode == ExecutionMode.MULTI_STEP:
                execute_multi_step_plan(
                    user_input,
                    planner,
                    executor,
                    reflector,
                    tui,
                    memory,
                    logger
                )
            else:
                execute_single_turn(
                    user_input,
                    agent,
                    executor,
                    tui,
                    memory,
                    logger
                )

            tui.print_separator()

        except KeyboardInterrupt:
            tui.print_system_message("\nInterrupted. Type 'quit' to exit.", "warning")
            continue
        except Exception as e:
            tui.print_system_message(f"Error: {e}", "error")
            import traceback
            traceback.print_exc()
            logger.log_error("runtime", str(e), {"traceback": traceback.format_exc()})
            continue

    # Cleanup
    if autonomy_loop:
        autonomy_loop.stop()
    if scheduler:
        scheduler.stop()


if __name__ == "__main__":
    main()
