"""
Validator module - Tool validation and safety enforcement.

Validates tool parameters before execution and enforces safety rules.
"""
import re
import shutil
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of tool validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    blocked: bool = False
    block_reason: Optional[str] = None

    def __init__(self, is_valid: bool = True):
        self.is_valid = is_valid
        self.errors = []
        self.warnings = []
        self.blocked = False
        self.block_reason = None

    def add_error(self, error: str):
        """Add validation error."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str):
        """Add validation warning."""
        self.warnings.append(warning)

    def block(self, reason: str):
        """Block execution for safety."""
        self.blocked = True
        self.block_reason = reason
        self.is_valid = False


class ToolValidator:
    """Validates tool calls before execution."""

    # Dangerous command patterns
    DANGEROUS_PATTERNS = [
        # Destructive operations
        r'rm\s+-rf\s+/',
        r'rm\s+.*-rf.*~/\.',
        r'mkfs\.\w+',
        r'dd\s+if=/dev/zero',
        r'>\s*/dev/sd\w',
        r':\(\)\{:\|:\&\};:',  # Fork bomb
        r'\.\s*/\w+.*\|.*sh',  # Piped to shell

        # System shutdown
        r'shutdown\s+-h',
        r'poweroff',
        r'halt\s+-p',
        r'init\s+0',
        r'systemctl\s+poweroff',

        # Privilege escalation (with warning)
        r'^sudo\s+',

        # Network attacks
        r'ping\s+-f',  # Flood ping

        # Data exfiltration risks
        r'curl\s+.*\|.*bash',
        r'wget\s+.*\|.*sh',
        r'fetch\s+.*\|.*sh',
    ]

    # Commands requiring confirmation in strict mode
    SENSITIVE_COMMANDS = [
        'rm', 'rmdir', 'del',
        'mv', 'move',
        'cp', 'copy',
        'chmod', 'chown',
    ]

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode

    def validate(self, tool_name: str, args: Dict[str, Any]) -> ValidationResult:
        """
        Validate a tool call.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            ValidationResult with validation status
        """
        result = ValidationResult()

        # Check tool exists
        if tool_name not in ['run_command', 'open_app']:
            result.add_error(f"Unknown tool: {tool_name}")
            return result

        # Tool-specific validation
        if tool_name == 'run_command':
            self._validate_run_command(args, result)
        elif tool_name == 'open_app':
            self._validate_open_app(args, result)

        return result

    def _validate_run_command(self, args: Dict[str, Any], result: ValidationResult):
        """Validate run_command tool."""
        # Check required parameters
        if 'command' not in args:
            result.add_error("Missing required parameter: 'command'")
            return

        command = args['command']

        # Type validation
        if not isinstance(command, str):
            result.add_error(f"Parameter 'command' must be string, got {type(command)}")
            return

        if not command.strip():
            result.add_error("Command cannot be empty")
            return

        cmd_lower = command.lower().strip()

        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                result.block(f"Dangerous command pattern detected: {pattern}")
                return

        # Check for sudo in strict mode
        if self.strict_mode and cmd_lower.startswith('sudo '):
            result.block("Sudo commands blocked in strict mode")
            return

        # Check base command exists
        base_cmd = cmd_lower.split()[0]
        if not shutil.which(base_cmd) and base_cmd not in ['cd', 'echo', 'exit']:
            result.add_warning(f"Command may not exist: {base_cmd}")

        # Check for sensitive commands
        if any(cmd_lower.startswith(sc) for sc in self.SENSITIVE_COMMANDS):
            result.add_warning(f"Sensitive command: {base_cmd}")

    def _validate_open_app(self, args: Dict[str, Any], result: ValidationResult):
        """Validate open_app tool."""
        # Check required parameters
        if 'app_name' not in args:
            result.add_error("Missing required parameter: 'app_name'")
            return

        app_name = args['app_name']

        # Type validation
        if not isinstance(app_name, str):
            result.add_error(f"Parameter 'app_name' must be string, got {type(app_name)}")
            return

        if not app_name.strip():
            result.add_error("App name cannot be empty")
            return

        # URL validation
        if app_name.startswith('http'):
            # Validate URL format
            if not re.match(r'^https?://[^\s]+$', app_name):
                result.add_error("Invalid URL format")

    def validate_plan_steps(self, steps: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Validate all steps in a plan.

        Returns:
            Tuple of (all_valid, list of errors)
        """
        all_errors = []

        for step in steps:
            action = step.get('action')
            args = step.get('args', {})
            step_id = step.get('id', '?')

            result = self.validate(action, args)
            if not result.is_valid:
                for error in result.errors:
                    all_errors.append(f"Step {step_id}: {error}")

        return len(all_errors) == 0, all_errors


class ParameterValidator:
    """Validates parameters against schemas."""

    def validate_type(self, value: Any, expected_type: str) -> bool:
        """Validate parameter type."""
        type_map = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict
        }

        if expected_type not in type_map:
            return True  # Unknown type, allow

        expected = type_map[expected_type]
        return isinstance(value, expected)

    def validate_required(self, args: Dict, required: List[str]) -> List[str]:
        """Check all required parameters are present."""
        errors = []
        for param in required:
            if param not in args:
                errors.append(f"Missing required parameter: '{param}'")
        return errors
