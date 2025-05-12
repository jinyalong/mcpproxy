import logging
import asyncio
import uuid
import json
import time
import os

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import StreamingResponse, JSONResponse
import uvicorn
from mcp import ClientSession, stdio_client, types
from mcp import StdioServerParameters

from jsonrpc import (
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, 
    INTERNAL_ERROR, SERVER_ERROR_START, create_error_response, 
    create_success_response, create_notification, validate_request
)
from config import get_server_params, AUTH_KEY
from proxy import MCPProxy, serialize_result

# Configure logging with more details
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log environment information at startup
logger.info("Starting server with environment:")
for key, value in os.environ.items():
    logger.info(f"ENV: {key}={value}")

# Get configurations
try:
    params = get_server_params()
    logger.info(f"Server parameters initialized: {params}")
except Exception as e:
    logger.error(f"Failed to get server parameters: {e}")
    raise

# 控制是否使用共享会话的环境变量
SHARED_SESSION = os.environ.get('SHARED_SESSION', 'true').lower() == 'true'
logger.info(f"Shared session mode: {SHARED_SESSION}")

# Global variables
global_client_session = None
global_stdio_client = None
global_streams = None
active_sessions = {}  # Store active SSE sessions

# Initialize proxy
proxy = MCPProxy(shared_session=SHARED_SESSION)

async def initialize_global_session():
    """初始化全局MCP客户端会话"""
    global global_client_session, global_stdio_client, global_streams
    try:
        logger.info("Initializing global MCP session...")
        global_stdio_client = stdio_client(params)
        logger.info("Created stdio client")
        global_streams = await global_stdio_client.__aenter__()
        logger.info("Entered stdio client context")
        global_client_session = await ClientSession(global_streams[0], global_streams[1]).__aenter__()
        logger.info("Global MCP session initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize global MCP session: {e}", exc_info=True)
        raise

async def cleanup_global_session():
    """清理全局MCP客户端会话"""
    global global_client_session, global_stdio_client, global_streams
    try:
        if global_client_session:
            await global_client_session.__aexit__(None, None, None)
        if global_stdio_client:
            await global_stdio_client.__aexit__(None, None, None)
        global_client_session = None
        global_stdio_client = None
        global_streams = None
        logger.info("Global MCP session cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during global session cleanup: {e}")

def validate_server_key(request) -> tuple[bool, JSONResponse | None]:
    """验证服务器密钥
    
    Returns:
        tuple[bool, JSONResponse | None]: (验证是否通过, 错误响应)
    """
    if AUTH_KEY is not None:
        client_key = request.query_params.get("auth_key")
        if not client_key:
            return False, JSONResponse(
                create_error_response(
                    SERVER_ERROR_START,
                    "Server key is required but not provided",
                    None
                ),
                status_code=401
            )
        if client_key != AUTH_KEY:
            return False, JSONResponse(
                create_error_response(
                    SERVER_ERROR_START,
                    "Invalid server key",
                    None
                ),
                status_code=401
            )
    return True, None

def get_session_params(request):
    """从请求参数中获取配置，并覆盖环境变量配置
    
    基于 get_server_params() 返回的 StdioServerParameters 对象，
    使用请求参数覆盖其中的环境变量值
    """
    base_params = get_server_params()
    
    # 获取所有查询参数
    query_params = dict(request.query_params)
    
    # 移除特殊参数
    query_params.pop('auth_key', None)
    
    # 更新环境变量
    new_env = dict(base_params.env)
    new_env.update(query_params)
    
    # 返回新的 StdioServerParameters，保持 command 和 args 不变
    return StdioServerParameters(
        command=base_params.command,
        args=base_params.args,
        env=new_env
    )

class SSESession:
    def __init__(self, session_id, params):
        self.session_id = session_id
        self.message_queue = asyncio.Queue()
        self.closed = False
        self.client_session = None
        self.streams = None
        self.stdio_client = None
        self._init_task = None
        self._cleanup_lock = asyncio.Lock()
        self.is_initialized = False
        self.params = params

    async def send_message(self, message):
        if not self.closed:
            logger.info(f"Queuing message for SSE client: {message}")
            await self.message_queue.put(message)

    async def handle_server_message(self, message):
        """Handle messages from the server"""
        try:
            logger.info(f"Received server message: {message}")
            if isinstance(message, types.ServerNotification):
                # Handle server notifications
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {
                        "level": "info",
                        "data": {
                            "type": message.root.__class__.__name__,
                            "content": serialize_result(message.root)
                        }
                    }
                }
                logger.info(f"Processing server notification: {notification}")
                await self.send_message(notification)

            elif isinstance(message, Exception):
                # Handle errors
                error = {
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {
                        "level": "error",
                        "data": {
                            "type": "error",
                            "message": str(message)
                        }
                    }
                }
                logger.info(f"Processing server error: {error}")
                await self.send_message(error)

        except Exception as e:
            logger.error(f"Error handling server message: {e}")
            # 发送错误通知
            error = {
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": {
                    "level": "error",
                    "data": {
                        "type": "error",
                        "message": f"Error handling server message: {str(e)}"
                    }
                }
            }
            await self.send_message(error)

    async def initialize_client(self):
        """初始化客户端连接"""
        if self.is_initialized:
            return
            
        self._init_task = asyncio.current_task()
        
        if not SHARED_SESSION:
            try:
                logger.info(f"Initializing dedicated session for {self.session_id}")
                self.stdio_client = stdio_client(self.params)
                self.streams = await self.stdio_client.__aenter__()
                self.client_session = await ClientSession(
                    self.streams[0], 
                    self.streams[1],
                    message_handler=self.handle_server_message
                ).__aenter__()
                self.is_initialized = True
                logger.info(f"Dedicated session initialized for {self.session_id}")
            except Exception as e:
                logger.error(f"Failed to initialize dedicated session: {e}")
                raise
        else:
            self.is_initialized = True

    async def close(self):
        """关闭会话"""
        if self.closed:
            return
            
        self.closed = True

        if not SHARED_SESSION:
            # 确保只在初始化的 task 中执行清理
            if self._init_task and self._init_task != asyncio.current_task():
                loop = asyncio.get_event_loop()
                done = loop.create_future()
                
                def _schedule_cleanup():
                    if not done.done():
                        done.set_result(None)
                
                # 在初始化 task 中调度清理
                self._init_task.get_loop().call_soon_threadsafe(_schedule_cleanup)
                await done
                
                # 等待初始化 task 完成清理
                while self.client_session is not None or self.stdio_client is not None:
                    await asyncio.sleep(0.1)
            else:
                # 在初始化 task 中，直接执行清理
                try:
                    if self.client_session:
                        await self.client_session.__aexit__(None, None, None)
                        self.client_session = None
                    
                    if self.stdio_client:
                        await self.stdio_client.__aexit__(None, None, None)
                        self.stdio_client = None
                    
                    self.streams = None
                except Exception as e:
                    logger.error(f"Error during cleanup: {e}")


async def sse_stream(session):
    """SSE stream handler"""
    try:
        # Send initial message with message endpoint URL
        messages_url = f"/messages?session_id={session.session_id}"
        logger.info(f"Starting SSE stream for session {session.session_id}")
        yield f"event: endpoint\ndata: {messages_url}\n\n"

        # Send a comment every 30 seconds to keep the connection alive
        keep_alive_task = asyncio.create_task(send_keep_alive(session))
        
        try:
            while not session.closed:
                message = await session.message_queue.get()
                if message is None:
                    break
                if isinstance(message, dict):
                    message = json.dumps(message)
                logger.debug(f"Sending message to client {session.session_id}: {message}")
                yield f"data: {message}\n\n"
        finally:
            keep_alive_task.cancel()
            try:
                await keep_alive_task
            except asyncio.CancelledError:
                pass
            
    except Exception as e:
        logger.error(f"SSE stream error for session {session.session_id}: {e}", exc_info=True)
    finally:
        logger.info(f"SSE stream ended for session {session.session_id}")
        await proxy.cleanup_session(session.session_id)

async def send_keep_alive(session):
    """Send keep-alive comments periodically"""
    try:
        while not session.closed:
            await asyncio.sleep(30)
            await session.message_queue.put({
                "jsonrpc": "2.0",
                "method": "ping",
                "params": {
                    "timestamp": int(time.time())
                }
            })
    except asyncio.CancelledError:
        pass

async def handle_sse(request):
    """Handle SSE connections"""
    logger.info(f"New SSE connection request from {request.client}")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Request query params: {dict(request.query_params)}")
    
    # Validate server key
    is_valid, error_response = proxy.validate_server_key(
        request.query_params.get("auth_key"),
        AUTH_KEY
    )
    if not is_valid:
        logger.warning(f"Invalid server key from {request.client}")
        return error_response
        
    session_id = str(uuid.uuid4())
    logger.info(f"Created new session {session_id} for client {request.client}")
    
    # Get session parameters
    session_params = proxy.get_session_params(params, request.query_params) if not SHARED_SESSION else params
    logger.info(f"Session parameters for {session_id}: {session_params}")
    
    try:
        session = await proxy.create_session(session_id, session_params)
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        return JSONResponse(
            create_error_response(INTERNAL_ERROR, "Failed to create session"),
            status_code=500
        )

    response = StreamingResponse(
        sse_stream(session),
        media_type="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Access-Control-Allow-Origin"] = "*"
    logger.info(f"SSE response prepared for session {session_id}")
    return response


# Predefined method handlers mapping
METHOD_HANDLERS = {
    "initialize": lambda session, params: session.initialize(),
    "tools/list": lambda session, params: session.list_tools(),
    "tools/call": lambda session, params: session.call_tool(params.get("name"), params.get("arguments")),
    "prompts/list": lambda session, params: session.list_prompts(),
    "prompts/get": lambda session, params: session.get_prompt(params.get("name"), params.get("arguments")),
    "resources/list": lambda session, params: session.list_resources(),
    "resources/templates/list": lambda session, params: session.list_resource_templates(),
    "resources/read": lambda session, params: session.read_resource(params.get("uri")),
    "resources/subscribe": lambda session, params: session.subscribe_resource(params.get("uri")),
    "resources/unsubscribe": lambda session, params: session.unsubscribe_resource(params.get("uri")),
}

async def handle_message(request):
    """Handle JSON-RPC 2.0 messages"""
    try:
        session_id = request.query_params.get("session_id")
        data = await request.json()
        return await proxy.handle_message(session_id, data)
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        return JSONResponse(
            create_error_response(INTERNAL_ERROR, str(e)),
            status_code=500
        )


# Create Starlette application
app = Starlette(
    routes=[
        Route("/sse", handle_sse),
        Route("/messages", handle_message, methods=["POST"]),
    ]
)

@app.on_event("startup")
async def startup_event():
    """Initialize global MCP session on startup"""
    if SHARED_SESSION:
        await proxy.initialize_global_session(params)
    else:
        logger.info("Running in dedicated session mode - skipping global session initialization")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup global MCP session on shutdown"""
    if SHARED_SESSION:
        await proxy.cleanup_global_session()

if __name__ == "__main__":
    # Configure uvicorn with appropriate settings
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        timeout_keep_alive=120,
        access_log=True
    )
    server = uvicorn.Server(config)
    server.run()
