import logging
import asyncio
import uuid
import json
import time
from typing import Dict, Optional, Tuple

from starlette.responses import JSONResponse
from mcp import ClientSession, stdio_client, types
from mcp import StdioServerParameters

from jsonrpc import (
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, 
    INTERNAL_ERROR, SERVER_ERROR_START, create_error_response, 
    create_success_response, validate_request
)

logger = logging.getLogger(__name__)

class SSESession:
    def __init__(self, session_id: str, params: StdioServerParameters):
        self.session_id = session_id
        self.message_queue = asyncio.Queue()
        self.closed = False
        self.client_session: Optional[ClientSession] = None
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
                # 使用 model_dump() 序列化 Pydantic 模型
                content = message.root.model_dump()
                # 确保消息符合 JSON-RPC 2.0 格式
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {
                        "level": "info",
                        "data": {
                            "type": message.root.__class__.__name__,
                            "content": content
                        }
                    }
                }
                await self.send_message(notification)
            elif isinstance(message, Exception):
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
                await self.send_message(error)
        except Exception as e:
            logger.error(f"Error handling server message: {e}")
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
        """Initialize client connection"""
        if self.is_initialized:
            return
            
        self._init_task = asyncio.current_task()
        
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

    async def close(self):
        """Close session"""
        if self.closed:
            return
            
        self.closed = True

        if self._init_task and self._init_task != asyncio.current_task():
            loop = asyncio.get_event_loop()
            done = loop.create_future()
            
            def _schedule_cleanup():
                if not done.done():
                    done.set_result(None)
            
            self._init_task.get_loop().call_soon_threadsafe(_schedule_cleanup)
            await done
            
            while self.client_session is not None or self.stdio_client is not None:
                await asyncio.sleep(0.1)
        else:
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

class MCPProxy:
    def __init__(self, shared_session: bool = True):
        self.shared_session = shared_session
        self.global_client_session: Optional[ClientSession] = None
        self.global_stdio_client = None
        self.global_streams = None
        self.active_sessions: Dict[str, SSESession] = {}

    async def initialize_global_session(self, params: StdioServerParameters):
        """Initialize global MCP client session"""
        try:
            logger.info("Initializing global MCP session...")
            self.global_stdio_client = stdio_client(params)
            self.global_streams = await self.global_stdio_client.__aenter__()
            self.global_client_session = await ClientSession(
                self.global_streams[0], 
                self.global_streams[1]
            ).__aenter__()
            logger.info("Global MCP session initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize global MCP session: {e}", exc_info=True)
            raise

    async def cleanup_global_session(self):
        """Cleanup global MCP client session"""
        try:
            if self.global_client_session:
                await self.global_client_session.__aexit__(None, None, None)
            if self.global_stdio_client:
                await self.global_stdio_client.__aexit__(None, None, None)
            self.global_client_session = None
            self.global_stdio_client = None
            self.global_streams = None
            logger.info("Global MCP session cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during global session cleanup: {e}")

    def validate_server_key(self, auth_key: Optional[str], required_key: Optional[str]) -> Tuple[bool, Optional[JSONResponse]]:
        """Validate server key"""
        if required_key is not None:
            if not auth_key:
                return False, JSONResponse(
                    create_error_response(
                        SERVER_ERROR_START,
                        "Server key is required but not provided",
                        None
                    ),
                    status_code=401
                )
            if auth_key != required_key:
                return False, JSONResponse(
                    create_error_response(
                        SERVER_ERROR_START,
                        "Invalid server key",
                        None
                    ),
                    status_code=401
                )
        return True, None

    def get_session_params(self, base_params: StdioServerParameters, query_params: dict) -> StdioServerParameters:
        """Get session parameters from request"""
        # Remove special parameters
        query_params = dict(query_params)
        query_params.pop('auth_key', None)
        
        # Update environment variables
        new_env = dict(base_params.env)
        new_env.update(query_params)
        
        return StdioServerParameters(
            command=base_params.command,
            args=base_params.args,
            env=new_env
        )

    async def create_session(self, session_id: str, params: StdioServerParameters) -> SSESession:
        """Create a new session"""
        session = SSESession(session_id, params)
        self.active_sessions[session_id] = session
        
        if not self.shared_session:
            try:
                await session.initialize_client()
            except Exception as e:
                logger.error(f"Failed to initialize client session: {e}")
                raise
        
        return session

    async def cleanup_session(self, session_id: str):
        """Cleanup session"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            await session.close()
            del self.active_sessions[session_id]
            logger.info(f"Session {session_id} removed from active sessions")

    async def handle_message(self, session_id: str, data: dict) -> JSONResponse:
        """Handle JSON-RPC 2.0 messages"""
        try:
            if session_id not in self.active_sessions:
                return JSONResponse(create_error_response(SERVER_ERROR_START, "Invalid session", None))
                
            session = self.active_sessions[session_id]
            
            if not session.is_initialized:
                await session.initialize_client()

            client_session = self.global_client_session if self.shared_session else session.client_session
            if not client_session:
                return JSONResponse(create_error_response(INTERNAL_ERROR, "MCP session not initialized"))

            # Validate JSON-RPC request
            is_valid, error_response = validate_request(data)
            if not is_valid:
                return JSONResponse(error_response)

            method = data.get("method")
            params = data.get("params", {})
            id = data.get("id")

            try:
                handler = METHOD_HANDLERS.get(method)
                if not handler:
                    return JSONResponse(create_error_response(METHOD_NOT_FOUND, f"Method '{method}' not found", id))

                resp = await handler(client_session, params)
                # 使用 model_dump() 序列化 Pydantic 模型
                if hasattr(resp, 'model_dump'):
                    resp = resp.model_dump()
                
                # Ensure capabilities have the correct structure for initialize response
                if method == "initialize" and isinstance(resp, dict):
                    if "capabilities" in resp:
                        capabilities = resp["capabilities"]
                        if capabilities.get("experimental") is None:
                            capabilities["experimental"] = {}
                        if capabilities.get("logging") is None:
                            capabilities["logging"] = {}
                        if capabilities.get("prompts") is None:
                            capabilities["prompts"] = {}
                        if capabilities.get("resources") is None:
                            capabilities["resources"] = {}
                        if "tools" in capabilities and capabilities["tools"].get("listChanged") is None:
                            capabilities["tools"]["listChanged"] = False
                        if resp.get("instructions") is None:
                            resp["instructions"] = ""
                
                # Ensure nextCursor is a string in list responses
                if method in ["tools/list", "prompts/list", "resources/list", "resources/templates/list"] and isinstance(resp, dict):
                    if resp.get("nextCursor") is None:
                        resp["nextCursor"] = ""
                
                await session.send_message(create_success_response(resp, id))
                return JSONResponse(create_success_response("ok", id))

            except TypeError as e:
                return JSONResponse(create_error_response(INVALID_PARAMS, str(e), id))
            except Exception as e:
                logger.error(f"Error processing method {method}: {e}")
                return JSONResponse(create_error_response(INTERNAL_ERROR, str(e), id))
                
        except json.JSONDecodeError:
            return JSONResponse(create_error_response(PARSE_ERROR, "Parse error"))
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return JSONResponse(create_error_response(INTERNAL_ERROR, str(e), data.get("id") if isinstance(data, dict) else None))

def serialize_result(result):
    """Serialize result to JSON-compatible format"""
    if result is None:
        return None
    elif isinstance(result, (str, int, float, bool)):
        return result
    elif isinstance(result, (list, tuple)):
        return [serialize_result(item) for item in result]
    elif isinstance(result, dict):
        return {k: serialize_result(v) for k, v in result.items()}
    elif hasattr(result, '__dict__'):
        return {k: serialize_result(v) for k, v in result.__dict__.items() if not k.startswith('_')}
    else:
        return str(result)

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