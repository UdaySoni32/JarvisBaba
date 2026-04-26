"""
Terminal tool - Execute shell commands safely.
"""
import subprocess
import shlex
from typing import Union


def run_command(command: str) -> dict:
    """
    Execute a shell command and return the result.

    Args:
        command: The shell command to execute

    Returns:
        dict with stdout, stderr, returncode, and success status
    """
    try:
        # Security: don't allow dangerous commands
        dangerous = ['rm -rf /', 'mkfs', 'dd if=/dev/zero', '>:', '| sh', '; sh']
        for d in dangerous:
            if d in command.lower():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Blocked potentially dangerous command: {d}",
                    "returncode": -1
                }

        # Execute command with timeout
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out after 30 seconds",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }
