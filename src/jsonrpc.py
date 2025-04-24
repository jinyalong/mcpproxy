"""JSON-RPC 2.0 utilities and constants."""

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_ERROR_START = -32000
SERVER_ERROR_END = -32099


def create_error_response(code, message, id=None, data=None):
    """Create a JSON-RPC error response."""
    error = {
        "code": code,
        "message": message
    }
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "error": error,
        "id": id
    }


def create_success_response(result, id):
    """Create a JSON-RPC success response."""
    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": id
    }


def create_notification(method, params):
    """Create a JSON-RPC notification message."""
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params
    }


def validate_request(data):
    """Validate basic JSON-RPC 2.0 request structure.
    
    Args:
        data: The request data to validate
        
    Returns:
        tuple: (is_valid, error_response)
        If request is valid, error_response will be None
        If request is invalid, error_response will contain the error details
    """
    if not isinstance(data, dict):
        return False, create_error_response(INVALID_REQUEST, "Invalid Request")
        
    jsonrpc = data.get("jsonrpc")
    method = data.get("method")
    
    if jsonrpc != "2.0" or not method:
        return False, create_error_response(INVALID_REQUEST, "Invalid Request", data.get("id"))
    
    return True, None 