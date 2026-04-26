"""
Apps tool - Open applications based on the current platform.
"""
import subprocess
import platform
import shutil


def get_opener_command() -> list:
    """Get the appropriate command to open apps based on platform."""
    system = platform.system()

    if system == "Darwin":  # macOS
        return ["open"]
    elif system == "Linux":
        # Try common Linux openers
        for opener in ["xdg-open", "gnome-open", "kde-open"]:
            if shutil.which(opener):
                return [opener]
        return None
    elif system == "Windows":
        return ["start", ""]
    return None


def open_app(app_name: str) -> dict:
    """
    Open an application by name.

    Args:
        app_name: Name of the application to open (e.g., 'firefox', 'code', 'terminal')

    Returns:
        dict with success status and message
    """
    system = platform.system()
    opener = get_opener_command()

    if not opener and system != "Windows":
        return {
            "success": False,
            "message": f"No application opener found for {system}"
        }

    try:
        if system == "Darwin":  # macOS
            # macOS: use 'open -a' for apps, 'open' for files/URLs
            if app_name.startswith("http"):
                cmd = ["open", app_name]
            else:
                cmd = ["open", "-a", app_name]

        elif system == "Linux":
            # Linux: try common executables or use xdg-open
            if shutil.which(app_name):
                cmd = [app_name]
            elif app_name.startswith("http"):
                cmd = [*opener, app_name]
            else:
                # Try to find the app in common locations
                cmd = [*opener, app_name]

        elif system == "Windows":
            # Windows: use start command
            cmd = ["start", "", app_name]
            subprocess.run(cmd, shell=True, check=True)
            return {
                "success": True,
                "message": f"Opened {app_name} on Windows"
            }

        subprocess.run(cmd, check=True, capture_output=True)
        return {
            "success": True,
            "message": f"Opened {app_name}"
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "message": f"Failed to open {app_name}: {e.stderr.decode() if e.stderr else str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error opening {app_name}: {str(e)}"
        }
