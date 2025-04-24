import asyncio
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, LoggingLevel
from mcp.client.sse import sse_client


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_sse_server(self, server_url: str):
        """Connect to an MCP server running with SSE transport"""
        try:
            print(f"Connecting to {server_url}...")

            # Store the context managers so they stay alive
            self._streams_context = sse_client(url=server_url)
            streams = await self._streams_context.__aenter__()

            self._session_context = ClientSession(*streams)
            self.session = await self._session_context.__aenter__()

            # Initialize with a timeout to prevent hanging indefinitely
            print("Initializing SSE client...")
            try:
                await asyncio.wait_for(self.session.initialize(), timeout=30.0)
                print("Successfully initialized session")
            except asyncio.TimeoutError:
                print("Session initialization timed out, but continuing")


        except Exception as e:
            print(f"Connection error: {e}")
            # 确保清理资源
            await self.cleanup()
            raise

    async def cleanup(self):
        """Properly clean up the session and streams"""
        try:
            if hasattr(self, '_session_context') and self._session_context:
                await self._session_context.__aexit__(None, None, None)
            if hasattr(self, '_streams_context') and self._streams_context:
                await self._streams_context.__aexit__(None, None, None)
        except Exception as e:
            print(f"Cleanup error: {e}")


async def main():
    client = MCPClient()
    try:
        await client.connect_to_sse_server(server_url='your_server_url/sse?auth_key=your_auth_key')

        try:
            response = await asyncio.wait_for(client.session.list_tools(), timeout=10.0)
            print(f"Available tools: {[tool.name for tool in response.tools]}")
        except Exception as e:
            print(f"Error in loop: {e}")

    except Exception as e:
        print(f"Error in main: {e}")
    finally:
        print("Cleaning up resources...")
        await client.cleanup()
        print("Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())