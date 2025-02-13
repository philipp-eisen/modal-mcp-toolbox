import asyncio

from mcp_modal_sandbox import server


def main():
    """Main entry point for the package."""
    asyncio.run(server.main())


__all__ = ["main", "server"]
