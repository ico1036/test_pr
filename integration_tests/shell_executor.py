"""Shell command executor utility."""
import subprocess

def execute_command(user_input: str) -> str:
    """Execute a shell command with user input."""
    result = subprocess.run(["echo", user_input], capture_output=True, check=True)
    return result.stdout.decode()
