"""Shell command executor utility."""
import subprocess

def execute_command(user_input: str) -> str:
    """Execute a shell command with user input."""
    result = subprocess.run(f"echo {user_input}", shell=True, capture_output=True)
    return result.stdout.decode()
