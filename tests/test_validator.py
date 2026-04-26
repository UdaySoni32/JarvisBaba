"""
Test suite for tool validation and safety.
"""
import pytest
from core.validator import ToolValidator, ValidationResult


class TestToolValidator:
    """Test tool validation and safety enforcement."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = ToolValidator(strict_mode=False)
        self.strict_validator = ToolValidator(strict_mode=True)

    def test_valid_run_command(self):
        """Test that safe commands pass validation."""
        result = self.validator.validate("run_command", {"command": "ls -la"})
        assert result.is_valid is True
        assert result.blocked is False

    def test_valid_run_command_pwd(self):
        """Test pwd command passes."""
        result = self.validator.validate("run_command", {"command": "pwd"})
        assert result.is_valid is True

    def test_valid_open_app(self):
        """Test valid app opening."""
        result = self.validator.validate("open_app", {"app_name": "firefox"})
        assert result.is_valid is True

    def test_block_rm_rf_root(self):
        """Test dangerous rm -rf / is blocked."""
        result = self.validator.validate("run_command", {"command": "rm -rf /"})
        assert result.is_valid is False
        assert result.blocked is True

    def test_block_rm_rf_home(self):
        """Test rm -rf on home directory is blocked."""
        result = self.validator.validate("run_command", {"command": "rm -rf ~/"})
        assert result.blocked is True

    def test_block_shutdown(self):
        """Test shutdown commands are blocked."""
        result = self.validator.validate("run_command", {"command": "shutdown -h now"})
        assert result.blocked is True

    def test_block_poweroff(self):
        """Test poweroff is blocked."""
        result = self.validator.validate("run_command", {"command": "poweroff"})
        assert result.blocked is True

    def test_block_sudo_in_strict_mode(self):
        """Test sudo is blocked in strict mode."""
        result = self.strict_validator.validate("run_command", {"command": "sudo ls"})
        assert result.blocked is True

    def test_sudo_allowed_in_non_strict(self):
        """Test sudo is allowed when not in strict mode."""
        result = self.validator.validate("run_command", {"command": "sudo ls"})
        # Should not be blocked, but might have warning
        assert result.blocked is False

    def test_block_mkfs(self):
        """Test mkfs commands are blocked."""
        result = self.validator.validate("run_command", {"command": "mkfs.ext4 /dev/sda1"})
        assert result.blocked is True

    def test_block_dd_zero(self):
        """Test dd if=/dev/zero is blocked."""
        result = self.validator.validate("run_command", {"command": "dd if=/dev/zero of=/dev/sda"})
        assert result.blocked is True

    def test_block_fork_bomb(self):
        """Test fork bomb is blocked."""
        result = self.validator.validate("run_command", {"command": ":(){ :|:& };:"})
        assert result.blocked is True

    def test_missing_command_parameter(self):
        """Test missing required parameter."""
        result = self.validator.validate("run_command", {})
        assert result.is_valid is False
        assert "Missing required parameter" in result.errors[0]

    def test_missing_app_name_parameter(self):
        """Test missing app_name parameter."""
        result = self.validator.validate("open_app", {})
        assert result.is_valid is False

    def test_empty_command(self):
        """Test empty command is rejected."""
        result = self.validator.validate("run_command", {"command": ""})
        assert result.is_valid is False

    def test_unknown_tool(self):
        """Test unknown tool is rejected."""
        result = self.validator.validate("unknown_tool", {})
        assert result.is_valid is False
        assert "Unknown tool" in result.errors[0]

    def test_sensitive_command_warning(self):
        """Test sensitive commands generate warnings."""
        result = self.validator.validate("run_command", {"command": "rm file.txt"})
        assert result.is_valid is True
        assert len(result.warnings) > 0

    def test_validate_plan_steps(self):
        """Test batch validation of plan steps."""
        steps = [
            {"id": 1, "action": "run_command", "args": {"command": "ls"}},
            {"id": 2, "action": "run_command", "args": {"command": "rm -rf /"}},
        ]
        valid, errors = self.validator.validate_plan_steps(steps)
        assert valid is False
        assert len(errors) == 1
        assert "Step 2" in errors[0]


class TestParameterValidator:
    """Test parameter type validation."""

    def setup_method(self):
        from core.validator import ParameterValidator
        self.param_validator = ParameterValidator()

    def test_string_validation(self):
        """Test string type validation."""
        assert self.param_validator.validate_type("hello", "string")

    def test_integer_validation(self):
        """Test integer type validation."""
        assert self.param_validator.validate_type(42, "integer")

    def test_type_mismatch(self):
        """Test type mismatch detection."""
        assert not self.param_validator.validate_type(42, "string")

    def test_required_parameters(self):
        """Test required parameter checking."""
        errors = self.param_validator.validate_required(
            {"command": "ls"},
            ["command", "directory"]
        )
        assert len(errors) == 1
        assert "directory" in errors[0]
