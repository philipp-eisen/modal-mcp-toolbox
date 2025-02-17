import subprocess

from mcp import ErrorData, McpError
from mcp.types import INVALID_PARAMS

procs: dict[str, subprocess.Popen] = {}


def modal_start_serve(file_path: str):
    """Start the `modal serve` process for the given file path."""
    if file_path in procs:
        return

    proc = subprocess.Popen(["modal", "serve", file_path])
    procs[file_path] = proc
    return proc


def modal_stop_serve(file_path: str):
    """Stop the `modal serve` process for the given file path."""
    if file_path not in procs:
        return

    procs[file_path].terminate()
    del procs[file_path]


def modal_get_serve_stdout(file_path: str) -> str | None:
    """Get the stdout of the `modal serve` process for the given file path.
    Needs to be called after `modal_start_serve` and before `modal_stop_serve` for the given file path.
    """
    if file_path not in procs:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message=f"Modal server for {file_path} is not running. Use `modal_start_serve` to start it.",
            )
        )

    proc = procs[file_path]
    if not proc.stdout:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message=f"Modal server for {file_path} is not running. Use `modal_start_serve` to start it.",
            )
        )

    return proc.stdout.read().decode()
