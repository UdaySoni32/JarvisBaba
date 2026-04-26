"""
Tool Schema - Structured tool definitions for planner and agent.
Each tool exposes its name, description, and JSON Schema parameters.
"""
from typing import Dict, Any, List


def get_tool_schemas() -> List[Dict[str, Any]]:
    """
    Return structured schemas for all available tools.
    Used by planner and agent to understand tool capabilities.
    """
    return [
        {
            "name": "run_command",
            "description": "Execute a shell command and return stdout/stderr. "
                         "Use for file operations, system queries, git, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        },
        {
            "name": "open_app",
            "description": "Open an application or URL. "
                         "Use for launching browsers, editors, or any app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the app to open (e.g., 'firefox', 'code', 'terminal') "
                                     "or a URL starting with http"
                    }
                },
                "required": ["app_name"]
            }
        }
    ]


def get_tool_schemas_text() -> str:
    """Return tool schemas as formatted text for LLM prompts."""
    schemas = get_tool_schemas()
    lines = []
    for schema in schemas:
        lines.append(f"\nTool: {schema['name']}")
        lines.append(f"  Description: {schema['description']}")
        lines.append(f"  Parameters: {schema['parameters']}")
    return "\n".join(lines)


def validate_step(step: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate a plan step against tool schemas.
    Returns (is_valid, error_message).
    """
    schemas = get_tool_schemas()
    schema_map = {s["name"]: s for s in schemas}

    action = step.get("action")
    args = step.get("args", {})

    if action not in schema_map:
        return False, f"Unknown tool: {action}"

    schema = schema_map[action]
    required = schema["parameters"].get("required", [])

    for param in required:
        if param not in args:
            return False, f"Missing required parameter '{param}' for tool '{action}'"

    return True, ""
