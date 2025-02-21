from pathlib import Path
from typing import Annotated

import modal
from mcp import ErrorData, McpError
from mcp.types import INVALID_PARAMS, Annotations, TextContent
from pydantic import Field


async def run_python_code_in_sandbox(
    code: Annotated[str, Field(description="The python code to run.")],
    requirements: Annotated[list[str] | None, Field(description="The requirements to install.")] = None,
    python_version: Annotated[str, Field(description="The python version to use. If not provided defaults to 3.13")] = "3.13",
    mount_directory: Annotated[
        str | None,
        Field(
            description="Allows you to make a local directory available at `/mounted-dir` for the code in `code`. Needs to be an absolute path. "
            "Writes to this directory will NOT be reflected in the local directory."
        ),
    ] = None,
    pull_files: Annotated[
        list[tuple[str, str]] | None,
        Field(
            description="List of tuples (absolut_path_sandbox_file, absolute_path_local_file). "
            "When provided downloads the file(s) from the sandbox to the local file(s)."
        ),
    ] = None,
) -> TextContent:
    """
    Runs python code in a safe environment and returns the output.

    Usage:
       run_python_code_in_sandbox("print('Hello, world!')")
       run_python_code_in_sandbox("import requests\nprint(requests.get('https://icanhazip.com').text)", requirements=["requests"])
    """

    app = modal.App.lookup("mcp-toolbox--code", create_if_missing=True)
    image = modal.Image.debian_slim(python_version=python_version).pip_install(requirements or [])

    mounts: list[modal.Mount] = []
    if mount_directory:
        mounts.append(modal.Mount.from_local_dir(mount_directory, remote_path="/mounted-dir"))

    sb = modal.Sandbox.create(image=image, app=app, mounts=mounts)
    try:
        exc = sb.exec("python", "-c", code)
        exc.wait()
        if exc.returncode != 0:
            stderr = exc.stderr.read()
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Error running code:\n{stderr}",
                )
            )

        if pull_files:
            for remote_file, local_file in pull_files:
                if not Path(local_file).parent.exists():
                    Path(local_file).parent.mkdir(parents=True, exist_ok=True)

                if Path(local_file).exists():
                    raise McpError(
                        ErrorData(
                            code=INVALID_PARAMS,
                            message=f"File {local_file} already exists.",
                        )
                    )
                with sb.open(remote_file, "rb") as f:
                    with open(local_file, "wb") as f2:
                        f2.write(f.read())
        return TextContent(type="text", text=exc.stdout.read(), annotations=Annotations(audience=["user", "assistant"], priority=0.5))

    finally:
        sb.terminate()
