"""
Executor module - Handles tool execution with validation and state tracking.
"""
from typing import Any, Optional
from core.agent import AgentDecision
from core.state import StepState, StepStatus, ExecutionState
from core.validator import ToolValidator, ValidationResult


class ExecutionResult:
    """Result of tool execution."""

    def __init__(
        self,
        success: bool,
        action: Optional[str],
        result: Any,
        message: str,
        validation: Optional[ValidationResult] = None
    ):
        self.success = success
        self.action = action
        self.result = result
        self.message = message
        self.validation = validation

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "action": self.action,
            "result": self.result,
            "message": self.message,
            "blocked": self.validation.blocked if self.validation else False
        }


class Executor:
    """
    The Executor routes tool calls through validation before execution.
    Handles both single decisions and step-based execution.
    """

    def __init__(self, strict_mode: bool = False):
        self.tools = {}
        self.validator = ToolValidator(strict_mode=strict_mode)

    def register_tool(self, name: str, handler: callable) -> None:
        """Register a tool handler function."""
        self.tools[name] = handler

    def execute(self, decision: AgentDecision) -> ExecutionResult:
        """
        Execute the action from an agent decision.
        Validates before execution.
        """
        if not decision.requires_tool:
            return ExecutionResult(
                success=True,
                action=None,
                result=None,
                message="No tool execution needed"
            )

        # Validate
        validation = self.validator.validate(decision.action, decision.args)

        if not validation.is_valid:
            return ExecutionResult(
                success=False,
                action=decision.action,
                result=None,
                message=f"Validation failed: {validation.errors}",
                validation=validation
            )

        if validation.blocked:
            return ExecutionResult(
                success=False,
                action=decision.action,
                result=None,
                message=f"BLOCKED: {validation.block_reason}",
                validation=validation
            )

        # Execute
        return self._execute_tool(decision.action, decision.args, validation)

    def execute_step(self, step_state: StepState) -> ExecutionResult:
        """
        Execute a step state with full validation.
        Updates step_state with results.
        """
        # Mark step as running
        step_state.start()

        # Validate
        validation = self.validator.validate(step_state.action, step_state.args)

        if not validation.is_valid:
            error_msg = "; ".join(validation.errors)
            step_state.block(error_msg)
            step_state.validation_errors = validation.errors
            return ExecutionResult(
                success=False,
                action=step_state.action,
                result=None,
                message=f"Validation failed: {error_msg}",
                validation=validation
            )

        if validation.blocked:
            step_state.block(validation.block_reason)
            step_state.validation_errors = [validation.block_reason]
            return ExecutionResult(
                success=False,
                action=step_state.action,
                result=None,
                message=f"BLOCKED: {validation.block_reason}",
                validation=validation
            )

        # Execute
        result = self._execute_tool(step_state.action, step_state.args, validation)

        # Update step state
        if result.success:
            step_state.complete(result.result)
        else:
            step_state.fail(result.message)

        return result

    def _execute_tool(
        self,
        tool_name: str,
        tool_args: dict,
        validation: Optional[ValidationResult] = None
    ) -> ExecutionResult:
        """Internal method to execute a validated tool."""
        if tool_name not in self.tools:
            return ExecutionResult(
                success=False,
                action=tool_name,
                result=None,
                message=f"Unknown tool: {tool_name}",
                validation=validation
            )

        try:
            tool_handler = self.tools[tool_name]
            result = tool_handler(**tool_args)
            normalized_success = True
            if isinstance(result, dict) and "success" in result:
                normalized_success = bool(result.get("success"))

            return ExecutionResult(
                success=normalized_success,
                action=tool_name,
                result=result,
                message=f"Successfully executed {tool_name}" if normalized_success else f"{tool_name} reported failure",
                validation=validation
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                action=tool_name,
                result=None,
                message=f"Error executing {tool_name}: {str(e)}",
                validation=validation
            )

    def get_available_tools(self) -> list:
        """Return metadata about registered tools for LLM context."""
        tool_info = []
        for name, handler in self.tools.items():
            description = handler.__doc__ or f"Tool: {name}"
            tool_info.append({
                "name": name,
                "description": description.strip().split('\n')[0]
            })
        return tool_info

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self.tools
