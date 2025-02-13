from typing import Annotated

import mcp.server.stdio
import mcp.types as types
import modal
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, Field

server = Server("mcp-modal-sandbox")

TOOL_NAME = "run-python-code"


class RunPythonCodeSchema(BaseModel):
    code: Annotated[str, Field(description="The python code to run.")]
    requirements: Annotated[
        list[str], Field(description="The requirements to install")
    ] = []
    python_version: Annotated[str, Field(description="The python version to use")] = (
        "3.13"
    )

    def get_result(self):
        image = modal.Image.debian_slim(python_version=self.python_version).pip_install(
            self.requirements
        )
        sb = modal.Sandbox.create(image=image)
        exc = sb.exec("python", "-c", self.code)
        exc.wait()
        return exc.stdout.read()


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name=TOOL_NAME,
            description="Runs python code in a safe environment",
            inputSchema=RunPythonCodeSchema.model_json_schema(),
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if name != TOOL_NAME:
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    schema = RunPythonCodeSchema(**arguments)
    result = schema.get_result()

    return [types.TextContent(type="text", text=result)]


async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-modal-sandbox",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
