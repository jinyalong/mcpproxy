# MCP SSE Proxy Server

<p align="center">
  <img src="assets/logo.png" alt="MCP SSE Proxy Server Logo" width="200">
</p>

The MCP SSE Proxy Server is a Server-Sent Events (SSE) based Model Context Protocol (MCP) proxy server that enables remote execution of MCP servers using the standard MCP protocol. It supports both shared and independent session modes.

> Model Context Protocol (MCP) is an open protocol that standardizes how applications provide context to LLMs. Think of MCP like a USB-C port for AI applications. Just as USB-C provides a standardized way to connect your devices to various peripherals and accessories, MCP provides a standardized way to connect AI models to different data sources and tools.
>
> For more information about MCP:
> - [MCP Documentation (English)](https://modelcontextprotocol.io/introduction)
> - [MCP Documentation (中文)](https://docs.mcpservers.cn/introduction)
> - [MCP Server Gallery](https://mcpservers.cn/) - Discover and explore various MCP servers

[中文文档](README_zh.md)

## What Problems Does It Solve?

This project allows you to:
- Start and interact with any MCP server remotely using standard MCP protocol
- Maintain stable long connections through SSE
- Support multiple clients sharing a single MCP session or maintaining independent sessions
- Dynamically configure server environment through request parameters
- Quick deployment of STDIO processes via NPX and UVX

## System Architecture

<p align="center">
  <img src="assets/architecture.png" alt="MCP SSE Proxy Server Architecture">
</p>

## Features

- SSE long connection support for server push
- JSON-RPC 2.0 message format support
- Both shared and independent session modes
- Dynamic session environment configuration via request parameters
- Automatic connection keep-alive (30-second heartbeat)
- Complete error handling and logging
- Built-in support for NPX and UVX STDIO process deployment

## Integration & Customization

### Custom Docker Images

The MCP SSE Proxy Server is designed to be highly integrable into various custom Docker images. This flexibility allows you to create specialized environments for different use cases:

- **Browser Automation**: Integrate with Chrome/Chromium for browser-based MCP servers
- **Database Operations**: Bundle with specific databases for data manipulation MCP servers
- **Development Tools**: Package with development tools for code-related MCP servers
- **AI/ML Tools**: Include AI/ML libraries for machine learning MCP servers

### Advanced Routing

While the default configuration loads MCP server commands through environment variables, you can extend the functionality by:

1. **Multiple Server Integration**: Configure multiple MCP servers through a configuration file
2. **Dynamic Routing**: Add routing fields to SSE connections to direct traffic to different MCP servers
3. **Custom Router**: Build your own MCP router project by extending this base implementation

This flexibility allows you to:
- Create specialized MCP server clusters
- Implement load balancing across multiple servers
- Design custom routing logic based on your needs
- Build hierarchical MCP server architectures

## Configuration

### Environment Variables

- `SHARED_SESSION`: Controls session mode
  - `true`: Shared session mode (default), all clients share one MCP session
  - `false`: Independent session mode, each client creates a separate MCP session

- `AUTH_KEY`: Server access key
  - If set, all requests must provide this key
  - Passed via URL parameter `auth_key`

- `MCP_SERVER_CONFIG`: MCP server configuration
  Examples:
  ```bash
  # Run Node.js-based MCP server using NPX
  MCP_SERVER_CONFIG="npx -y @modelcontextprotocol/server-filesystem ."
  
  # Run Python-based MCP server using UVX
  MCP_SERVER_CONFIG="uvx mcp-server-fetch"
  ```

### Dynamic Configuration

In independent session mode (`SHARED_SESSION=false`), each SSE connection starts a new MCP server process. You can dynamically configure environment variables for each session through URL parameters:

```
GET /sse?auth_key=xxx&[CUSTOM_ENV]=value
```

This mechanism is particularly useful for scenarios requiring user-specific credentials. For example, when deploying a GitHub MCP server, different users can use their own Personal Access Tokens:

1. Configure the base command when deploying the server:
```bash
export MCP_SERVER_CONFIG="npx -y @modelcontextprotocol/server-github"
```

2. Users provide their tokens via URL when connecting:
```
GET /sse?auth_key=xxx&GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxxxxxxxxxxx
```

This way, you only need to deploy one MCP proxy server to serve multiple users, with each user using their own GitHub credentials. Other supported environment variable configurations:

- General Configuration:
  - `NODE_ENV`: Node.js environment (development/production)
  - `DEBUG`: Debug log level
  
- Server-Specific Configuration:
  - GitHub MCP Server: `GITHUB_PERSONAL_ACCESS_TOKEN`
  - Filesystem MCP Server: `ROOT_DIR`
  - Other server-specific environment variables

Note: Environment variables in URL parameters override server default configurations.

## API Endpoints

### SSE Connection
```
GET /sse?auth_key=xxx
```

After successfully establishing a connection, the server returns a message endpoint URL:
```
event: endpoint
data: /messages?session_id=<session_id>
```

### Message Sending
```
POST /messages?session_id=<session_id>
Content-Type: application/json

{
    "jsonrpc": "2.0",
    "method": "method_name",
    "params": {},
    "id": 1
}
```

## Supported Methods

- `initialize`: Initialize session
- `tools/list`: List available tools
- `tools/call`: Call a tool
- `prompts/list`: List available prompts
- `prompts/get`: Get a prompt
- `resources/list`: List resources
- `resources/templates/list`: List resource templates
- `resources/read`: Read a resource
- `resources/subscribe`: Subscribe to a resource
- `resources/unsubscribe`: Unsubscribe from a resource

## Running the Server

### Using Python

```bash
# Set environment variables
export AUTH_KEY=your_key
export SHARED_SESSION=true  # or false

# Start the server
python main.py
```

The server starts by default on `0.0.0.0:8000`.

### Using Docker

1. Pull the Docker image:
```bash
docker pull codefriday123/mcpproxy:1.0
```

2. Run the container:
```bash
docker run -d \
  -p 8000:8000 \
  -e AUTH_KEY=your_key \
  -e SHARED_SESSION=true \
  -e MCP_SERVER_CONFIG="npx -y @modelcontextprotocol/server-filesystem ." \
  codefriday123/mcpproxy:1.0
```

Environment variables:
- `AUTH_KEY`: Server access key (required)
- `SHARED_SESSION`: Session mode (default: true)
- `MCP_SERVER_CONFIG`: MCP server configuration command

The server will be available at `http://localhost:8000`.

### Using Alipay Cloud Run

You can also deploy the server on [Alipay Cloud Run](https://cloud.alipay.com/) (新人可免费使用容器资源):

<p align="center">
  <img src="assets/deploy.png" alt="MCP SSE Proxy Server Deployment on Alibaba Cloud">
</p>

1. Create a new service in Cloud Run
2. Configure the service with the following settings:
   - Image: `codefriday123/mcpproxy:1.0`
   - Port: `8000`
   - Environment variables:
     - `AUTH_KEY`: Your server access key
     - `SHARED_SESSION`: true/false
     - `MCP_SERVER_CONFIG`: Your MCP server configuration

3. Deploy the service

The server will be available at the provided Cloud Run endpoint.

## Logging

The server uses Python's logging module to record detailed logs, including:
- Environment variable information
- Connection establishment and closure
- Message processing
- Errors and exceptions

## Error Handling

The server uses the standard JSON-RPC 2.0 error response format:
```json
{
    "jsonrpc": "2.0",
    "error": {
        "code": error_code,
        "message": "error message"
    },
    "id": null
}
```

Main error codes:
- `-32700`: Parse error
- `-32600`: Invalid request
- `-32601`: Method not found
- `-32602`: Invalid params
- `-32603`: Internal error
- `-32000`: Server error

## Usage Examples

### Python Client

You can use the official MCP Python client to connect to a deployed MCP server:

```python
import asyncio
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, LoggingLevel
from mcp.client.sse import sse_client

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_sse_server(self, server_url: str):
        """Connect to an MCP server running SSE transport"""
        try:
            print(f"Connecting to {server_url}...")
            self._streams_context = sse_client(url=server_url)
            streams = await self._streams_context.__aenter__()
            self._session_context = ClientSession(*streams)
            self.session = await self._session_context.__aenter__()
            
            try:
                await asyncio.wait_for(self.session.initialize(), timeout=30.0)
                print("Session initialized successfully")
            except asyncio.TimeoutError:
                print("Session initialization timed out, but will continue")

        except Exception as e:
            print(f"Connection error: {e}")
            await self.cleanup()
            raise

    async def cleanup(self):
        """Properly clean up session and streams"""
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
        await client.connect_to_sse_server('http://your-server:8000/sse?auth_key=your_auth_key')
        response = await asyncio.wait_for(client.session.list_tools(), timeout=10.0)
        print(f"Available tools: {[tool.name for tool in response.tools]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

### Cursor Integration

You can also integrate with [Cursor](https://docs.cursor.com/context/model-context-protocol) by adding the server to Cursor's MCP configuration:

```json
{
  "mcpServers": {
    "server-name": {
      "url": "http://your-server:8000/sse?auth_key=your_auth_key",
      "env": {
      }
    }
  }
}
```

Place this configuration in one of these locations:
- `.cursor/mcp.json` in your project directory for project-specific access
- `~/.cursor/mcp.json` in your home directory for global access

## License

MIT License

## Contributing

Contributions are welcome! Feel free to submit Pull Requests.

## Roadmap

### Current Features
- Basic MCP server proxy functionality
- SSE transport support
- Shared and independent session modes
- Dynamic environment configuration
- Integration with Cursor and other MCP clients

### Future Plans
- **Stateless Architecture**
  - Tool-only mode for stateless operation
  - HTTP-based tool execution without session management
  - Simplified deployment and scaling
  - Reduced resource overhead
  - Improved reliability and maintainability

- **Agent Sandbox**
  - Create isolated environments for running MCP agents
  - Resource limits and monitoring
  - Security sandboxing for untrusted agents
  - Performance optimization for agent execution
  - Streamable HTTP support
    - Forward compatibility with streamable HTTP protocol
    - Hybrid mode: SSE + HTTP for enhanced flexibility
    - Protocol negotiation and fallback mechanisms
    - Optimized streaming performance

- **Agent Router**
  - Intelligent routing between multiple MCP servers
  - Load balancing and failover
  - Request/response transformation
  - Protocol version compatibility handling
  - Advanced routing rules and policies

- **Best Practices**
  - Deployment guides for different scenarios
  - Security recommendations
  - Performance optimization tips
  - Monitoring and logging best practices
  - Integration patterns with various MCP servers

Stay tuned for updates and new features!