"""Opt-in shell tool for FastMCP. Executes inside the MCP process namespace.

SECURITY: Arbitrary command execution. Do not enable on a public/untrusted MCP
endpoint. This tool inherits the service account's privileges and filesystem.
"""
import os
import subprocess

def register_shell_tool(mcp):
    @mcp.tool()
    def shell_exec(command: str, timeout_seconds: int = 15) -> dict:
        """Execute a shell command in the MCP runtime (not automatically on the host)."""
        if os.getenv("ENABLE_SHELL_EXEC") != "yes":
            return {"error": "shell_exec disabled; set ENABLE_SHELL_EXEC=yes explicitly"}
        if not isinstance(command, str) or not command.strip() or len(command) > 4096:
            return {"error": "command must be 1..4096 characters"}
        timeout = min(max(int(timeout_seconds), 1), 30)
        try:
            result = subprocess.run(
                ["/bin/sh", "-c", command],
                capture_output=True,
                timeout=timeout,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout[:16384].decode("utf-8", "replace"),
                "stderr": result.stderr[:16384].decode("utf-8", "replace"),
                "stdout_truncated": len(result.stdout) > 16384,
                "stderr_truncated": len(result.stderr) > 16384,
            }
        except subprocess.TimeoutExpired:
            return {"error": "command timed out", "timeout_seconds": timeout}
        except OSError as exc:
            return {"error": type(exc).__name__}
