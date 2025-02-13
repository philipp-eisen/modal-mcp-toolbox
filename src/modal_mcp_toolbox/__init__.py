import argparse
import logging
from importlib.metadata import version

from mcp.server.fastmcp import FastMCP

from modal_mcp_toolbox.code import run_python_code_in_sandbox
from modal_mcp_toolbox.flux import generate_flux_image

server = FastMCP("modal-toolbox")

server.add_tool(run_python_code_in_sandbox)
server.add_tool(generate_flux_image)


logger = logging.getLogger(__name__)


def main():
    """MCP Modal Sandbox: A sandbox for running python code in a safe environment."""
    parser = argparse.ArgumentParser(description="A sandbox for running python code in a safe environment.")
    parser.add_argument("--version", action="version", version=version("modal-mcp-toolbox"))
    parser.parse_args()
    server.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler()])
    main()
