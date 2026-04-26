"""
TUI module - Terminal User Interface using Rich.
Enhanced with diagnostic views for debugging and observability.
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.layout import Layout
from rich.syntax import Syntax
from typing import Optional, Dict, Any, List


class JarvisTUI:
    """Terminal User Interface for Jarvis with diagnostic capabilities."""

    def __init__(self, debug_mode: bool = False):
        self.console = Console()
        self.debug_mode = debug_mode
        self._setup_styles()

    def _setup_styles(self):
        """Define color schemes and styles."""
        self.styles = {
            "user": "bright_blue",
            "assistant": "bright_green",
            "thought": "dim italic",
            "action": "bright_yellow",
            "tool": "bright_cyan",
            "error": "bright_red",
            "success": "bright_green",
            "system": "bright_magenta",
            "border": "dim blue",
            "warning": "yellow",
            "blocked": "red",
            "info": "cyan"
        }

    def print_header(self):
        """Print the application header."""
        header = Panel(
            "[bold bright_blue]JARVIS[/bold bright_blue] [dim]-[/dim] [bright_green]Robust Agent System[/bright_green]\n"
            "[dim]Testable | Observable | Safe[/dim]",
            border_style=self.styles["border"],
            title="[dim]v2.0[/dim]",
            title_align="right"
        )
        self.console.print(header)

    def print_user_input(self, text: str):
        """Display user input."""
        panel = Panel(
            text,
            title="[bold]You[/bold]",
            title_align="left",
            border_style=self.styles["user"],
            padding=(1, 2)
        )
        self.console.print(panel)

    def print_thought(self, thought: str):
        """Display agent's reasoning."""
        panel = Panel(
            f"[italic dim]{thought}[/italic dim]",
            title="[dim]Thought[/dim]",
            title_align="left",
            border_style=self.styles["thought"]
        )
        self.console.print(panel)

    def print_action(self, action: str, args: Dict):
        """Display action being taken."""
        args_str = "\n".join([f"  {k}: {v}" for k, v in args.items()]) if args else "  (no arguments)"

        content = f"[bold]{action}[/bold]\n{args_str}"
        panel = Panel(
            content,
            title="[bold yellow]Action[/bold yellow]",
            title_align="left",
            border_style=self.styles["action"]
        )
        self.console.print(panel)

    def print_tool_output(self, result: Dict):
        """Display tool execution result."""
        success = result.get("success", False)
        action = result.get("action", "unknown")
        message = result.get("message", "")

        if result.get("blocked"):
            border = self.styles["blocked"]
            prefix = "[red bold]"
        elif success:
            border = self.styles["success"]
            prefix = "[green]"
        else:
            border = self.styles["error"]
            prefix = "[red]"

        panel = Panel(
            f"{prefix}{message}[/]",
            title=f"[bold cyan]Tool: {action}[/bold cyan]",
            title_align="left",
            border_style=border
        )
        self.console.print(panel)

    def print_response(self, response: str):
        """Display final assistant response."""
        panel = Panel(
            response,
            title="[bold green]Assistant[/bold green]",
            title_align="left",
            border_style=self.styles["assistant"],
            padding=(1, 2)
        )
        self.console.print(panel)

    # === DIAGNOSTIC DISPLAY METHODS ===

    def print_mode_classified(self, mode: str, reasoning: str, confidence: float):
        """Display mode classification result."""
        color = "green" if "multi" in mode else "blue"
        panel = Panel(
            f"[bold {color}]{mode}[/bold {color}] [dim](confidence: {confidence:.2f})[/dim]\n"
            f"[italic]{reasoning}[/italic]",
            title="[dim]Mode Classification[/dim]",
            title_align="left",
            border_style=color
        )
        self.console.print(panel)

    def print_goal(self, goal: str):
        """Display the execution goal."""
        panel = Panel(
            f"[bold bright_white]{goal}[/bold bright_white]",
            title="[bold]Goal[/bold]",
            title_align="left",
            border_style="bright_blue",
            padding=(1, 2)
        )
        self.console.print(panel)

    def print_execution_state(self, state):
        """Display execution state table."""
        if not state or not state.steps:
            self.console.print("[dim]No execution state[/dim]")
            return

        table = Table(title="[bold]Execution State[/bold]", show_header=True)
        table.add_column("Step", style="cyan", width=6)
        table.add_column("Tool", style="magenta", width=15)
        table.add_column("Status", style="yellow", width=12)
        table.add_column("Attempts", style="blue", width=10)
        table.add_column("Result", style="dim", width=30)

        for step in state.steps:
            status_style = {
                "pending": "dim",
                "running": "yellow",
                "success": "green",
                "failed": "red",
                "retry": "yellow",
                "skipped": "dim",
                "blocked": "red bold"
            }.get(step.status.value, "white")

            result_preview = ""
            if step.result:
                result_str = str(step.result)
                result_preview = result_str[:27] + "..." if len(result_str) > 30 else result_str
            elif step.error:
                result_preview = f"[red]{step.error[:27]}...[/red]"

            table.add_row(
                str(step.id),
                step.action,
                f"[{status_style}]{step.status.value}[/{status_style}]",
                f"{step.attempts}/{step.max_attempts}",
                result_preview
            )

        self.console.print(table)

    def print_plan(self, steps: List[Dict]):
        """Display the execution plan."""
        if not steps:
            self.console.print("[dim]No plan steps[/dim]")
            return

        tree = Tree("[bold]Plan[/bold]")

        for step in steps:
            step_id = step.get("id", "?")
            action = step.get("action", "?")
            args = step.get("args", {})

            status = step.get("status", "pending")
            status_mark = {
                "pending": ("○", "dim"),
                "running": ("◉", "yellow"),
                "success": ("✓", "green"),
                "failed": ("✗", "red"),
                "retry": ("↻", "yellow"),
                "skipped": ("⊘", "dim"),
                "blocked": ("⛔", "red bold")
            }.get(status, ("?", "white"))

            args_str = ", ".join(f"{k}={v}" for k, v in args.items()) if args else ""
            step_text = Text()
            step_text.append(f"{status_mark[0]} ", style=status_mark[1])
            step_text.append(f"Step {step_id}: ", style="bold")
            step_text.append(f"{action}", style="cyan")
            if args_str:
                step_text.append(f" ({args_str})", style="dim")

            tree.add(step_text)

        self.console.print(tree)

    def print_step_running(self, step_id: int, action: str, attempt: int):
        """Display step running status."""
        panel = Panel(
            f"[yellow]▶ Step {step_id}: {action}[/yellow]\n"
            f"[dim]Attempt {attempt}[/dim]",
            title="[dim]Execution[/dim]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1)
        )
        self.console.print(panel)

    def print_step_complete(self, step_id: int, action: str, status: str, message: str = ""):
        """Display step completion."""
        status_colors = {
            "success": "green",
            "failed": "red",
            "blocked": "red bold",
            "skipped": "dim"
        }
        color = status_colors.get(status, "white")

        panel = Panel(
            f"[{color}]Step {step_id}: {action} [{status}][/{color}]\n"
            f"[dim]{message}[/dim]",
            title="[dim]Result[/dim]",
            title_align="left",
            border_style=color,
            padding=(0, 1)
        )
        self.console.print(panel)

    def print_reflection_result(self, reflection):
        """Display reflection result."""
        status_colors = {
            "success": "green",
            "partial": "yellow",
            "failure": "red",
            "critical_failure": "red bold"
        }
        color = status_colors.get(reflection.status.value, "white")

        action_colors = {
            "continue": "blue",
            "retry": "yellow",
            "replan": "magenta",
            "stop": "red"
        }
        action_color = action_colors.get(reflection.next_action.value, "white")

        content = [
            f"[bold {color}]Status: {reflection.status.value}[/{color}] "
            f"[dim](confidence: {reflection.confidence:.2f})[/dim]",
            f"[italic]{reflection.reasoning}[/italic]",
            f"",
            f"Next: [{action_color}]{reflection.next_action.value}[/{action_color}]"
        ]

        if reflection.recovery_suggestion:
            content.append(f"[yellow]Suggestion: {reflection.recovery_suggestion}[/yellow]")

        panel = Panel(
            "\n".join(content),
            title="[dim]Reflection[/dim]",
            title_align="left",
            border_style="dim"
        )
        self.console.print(panel)

    def print_validation_error(self, step_id: int, errors: List[str]):
        """Display validation error."""
        error_text = "\n".join(f"[red]• {e}[/red]" for e in errors)
        panel = Panel(
            f"Step {step_id} validation failed:\n{error_text}",
            title="[bold red]Validation Error[/bold red]",
            title_align="left",
            border_style="red"
        )
        self.console.print(panel)

    def print_blocked_action(self, step_id: int, reason: str):
        """Display blocked action warning."""
        panel = Panel(
            f"[bold red]⛔ STEP {step_id} BLOCKED[/bold red]\n"
            f"[yellow]Reason: {reason}[/yellow]",
            title="[bold red]Safety Block[/bold red]",
            title_align="left",
            border_style="red"
        )
        self.console.print(panel)
        self.console.print("[dim]This command was prevented for your safety.[/dim]")

    def print_execution_summary(self, completed: int, failed: int, total: int, blocked: int = 0):
        """Display execution completion summary."""
        if failed == 0 and blocked == 0:
            color = "green"
            status = "COMPLETE"
        elif failed > 0 and failed < total:
            color = "yellow"
            status = "PARTIAL"
        else:
            color = "red"
            status = "FAILED"

        content = [f"[bold {color}]{status}: {completed}/{total} steps[/bold {color}]"]

        details = []
        if failed > 0:
            details.append(f"[red]{failed} failed[/red]")
        if blocked > 0:
            details.append(f"[red bold]{blocked} blocked[/red bold]")

        if details:
            content.append(f" ({', '.join(details)})")

        panel = Panel(
            "".join(content),
            title="[bold]Execution Summary[/bold]",
            title_align="left",
            border_style=color
        )
        self.console.print(panel)

    def print_tasks_panel(self, tasks: List[Dict[str, Any]], active_execution: Optional[Dict[str, Dict[str, Any]]] = None):
        """Display task table and active progress."""
        table = Table(title="[bold]Tasks[/bold]", show_header=True)
        table.add_column("ID", style="cyan", width=12)
        table.add_column("Goal", style="white", width=38)
        table.add_column("Status", style="yellow", width=10)
        table.add_column("Mode", style="magenta", width=12)

        for task in tasks:
            goal = task.get("goal", "")
            preview = goal[:35] + "..." if len(goal) > 38 else goal
            table.add_row(
                task.get("id", "")[:12],
                preview,
                task.get("status", "unknown"),
                task.get("mode", "foreground")
            )

        self.console.print(table)

        active_execution = active_execution or {}
        if active_execution:
            for task_id, data in active_execution.items():
                panel = Panel(
                    f"Task: [cyan]{task_id}[/cyan]\n"
                    f"Step: [yellow]{data.get('step_id', '?')}[/yellow]\n"
                    f"Action: [magenta]{data.get('action', '?')}[/magenta]\n"
                    f"Attempt: {data.get('attempt', 1)}",
                    title="[bold]Active Task Execution[/bold]",
                    border_style="yellow"
                )
                self.console.print(panel)

    def print_system_message(self, message: str, style: str = "info"):
        """Display system message."""
        color = {
            "info": "blue",
            "warning": "yellow",
            "error": "red",
            "success": "green"
        }.get(style, "blue")

        self.console.print(f"[{color}][System][/] {message}")

    def print_debug(self, source: str, data: Dict):
        """Display debug information."""
        if not self.debug_mode:
            return

        content = f"[cyan bold]DEBUG [{source}][/cyan bold]\n"
        for key, value in data.items():
            content += f"  {key}: {value}\n"

        panel = Panel(
            content,
            title="[dim]Debug Output[/dim]",
            title_align="left",
            border_style="dim cyan"
        )
        self.console.print(panel)

    def print_separator(self):
        """Print a separator line."""
        self.console.print()
        self.console.rule(style="dim blue")
        self.console.print()

    def get_input(self) -> str:
        """Get user input with styled prompt."""
        self.console.print("[bold bright_blue]>>>[/bold bright_blue]", end=" ")
        return input()

    def print_help(self):
        """Display help information."""
        table = Table(title="Available Commands")
        table.add_column("Command", style="bright_cyan")
        table.add_column("Description", style="white")

        table.add_row("quit, exit", "Exit Jarvis")
        table.add_row("clear", "Clear the screen")
        table.add_row("help", "Show this help message")
        table.add_row("logs", "Show execution summary")
        table.add_row("list tasks", "Show all tasks")
        table.add_row("pause task <id>", "Pause a pending/running task")
        table.add_row("resume task <id>", "Resume a paused task")
        table.add_row("cancel task <id>", "Cancel a task")
        table.add_row("", "")
        table.add_row("[dim]Any other text", "[dim]Processed by agent")

        self.console.print(table)

    def clear_screen(self):
        """Clear the terminal screen."""
        self.console.clear()
        self.print_header()

    def print_start_message(self, llm_name: str):
        """Print startup information."""
        self.print_header()
        self.print_system_message(f"Using LLM: {llm_name}", "success")
        self.print_system_message("Type 'help' for commands", "info")


class SimpleTUI:
    """Fallback simple TUI if rich is not available."""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def print_header(self):
        print("=" * 50)
        print("  JARVIS - Robust Agent System")
        print("=" * 50)

    def print_user_input(self, text: str):
        print(f"\n[YOU] {text}")

    def print_thought(self, thought: str):
        print(f"  [Thought] {thought}")

    def print_action(self, action: str, args: dict):
        print(f"  [Action] {action}({args})")

    def print_tool_output(self, result: dict):
        status = "OK" if result.get("success") else "FAIL"
        print(f"  [Tool] {status}: {result.get('message', '')}")

    def print_response(self, response: str):
        print(f"\n[ASSISTANT] {response}")

    def print_mode_classified(self, mode: str, reasoning: str, confidence: float):
        print(f"  [Mode] {mode} (conf: {confidence:.2f})")
        print(f"  [Reason] {reasoning}")

    def print_goal(self, goal: str):
        print(f"\n[GOAL] {goal}")

    def print_execution_state(self, state):
        print("\n--- Execution State ---")
        for step in state.steps:
            print(f"  Step {step.id}: {step.action} = {step.status.value}")

    def print_plan(self, steps: list):
        print("\n[PLAN]")
        for s in steps:
            print(f"  {s.get('id')}. {s.get('action')}")

    def print_step_running(self, step_id: int, action: str, attempt: int):
        print(f"  [Running] Step {step_id}: {action} (attempt {attempt})")

    def print_step_complete(self, step_id: int, action: str, status: str, msg: str = ""):
        print(f"  [{status.upper()}] Step {step_id}: {action}")
        if msg:
            print(f"    {msg}")

    def print_reflection_result(self, reflection):
        print(f"  [Reflection] {reflection.status.value} -> {reflection.next_action.value}")

    def print_validation_error(self, step_id: int, errors: list):
        print(f"  [Validation Error] Step {step_id}: {errors}")

    def print_blocked_action(self, step_id: int, reason: str):
        print(f"  [BLOCKED] Step {step_id}: {reason}")

    def print_execution_summary(self, completed: int, failed: int, total: int, blocked: int = 0):
        print(f"\n[SUMMARY] {completed}/{total} complete, {failed} failed, {blocked} blocked")

    def print_tasks_panel(self, tasks: list, active_execution: Optional[dict] = None):
        print("\n[TASKS]")
        for task in tasks:
            print(f"  {task.get('id', '')[:12]} | {task.get('status')} | {task.get('mode')} | {task.get('goal')}")
        active_execution = active_execution or {}
        for task_id, data in active_execution.items():
            print(
                f"  [ACTIVE] {task_id[:12]} step={data.get('step_id')} "
                f"action={data.get('action')} attempt={data.get('attempt')}"
            )

    def print_system_message(self, message: str, style: str = "info"):
        print(f"[SYSTEM] {message}")

    def print_separator(self):
        print("-" * 50)

    def get_input(self) -> str:
        return input(">>> ")

    def print_help(self):
        print("Commands: quit, exit, clear, help, logs, list tasks, list scheduled, list events,")
        print("          pause/resume/cancel task <id>, trigger <event_name>,")
        print("          enable/disable autonomy, autonomy status")

    def clear_screen(self):
        import os
        os.system('clear' if os.name != 'nt' else 'cls')
        self.print_header()

    def print_start_message(self, llm_name: str):
        self.print_header()
        print(f"Using: {llm_name}")

    def print_debug(self, source: str, data: dict):
        if self.debug_mode:
            print(f"[DEBUG {source}] {data}")


# Try to use Rich, fall back to simple
try:
    import rich
    TUI = JarvisTUI
except ImportError:
    TUI = SimpleTUI
