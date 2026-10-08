import subprocess
import sys
import os

class ExecutionResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.success = returncode == 0

def run_command(cmd, cwd=None, timeout=600, shell=False):
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=shell,
            encoding="utf-8",
            errors="replace",
        )
        return ExecutionResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as e:
        return ExecutionResult(124, e.stdout or "", e.stderr or "Command timed out")
    except FileNotFoundError:
        return ExecutionResult(127, "", f"Command not found: {cmd}")
