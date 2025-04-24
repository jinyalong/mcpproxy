import os
import shlex
import logging
from typing import List, Dict, NamedTuple, Optional
from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

# Configure logging
logger = logging.getLogger(__name__)

# 全局服务器密钥
AUTH_KEY: Optional[str] = os.getenv('AUTH_KEY')
if AUTH_KEY is None:
    logger.warning("AUTH_KEY environment variable is not set")



def parse_server_config(config_str: str) -> tuple[str, List[str]]:
    """解析服务器配置字符串为命令和参数列表"""
    parts = shlex.split(config_str)
    if not parts:
        raise ValueError("Empty server config")
    return parts[0], parts[1:]

def get_server_params() -> StdioServerParameters:
    """获取服务器参数配置
    
    从环境变量获取配置：
    - MCP_SERVER_CONFIG: 完整的命令配置字符串
    - 其他所有环境变量都会被传递给子进程
    
    Raises:
        ValueError: 当 MCP_SERVER_CONFIG 环境变量未设置时抛出
    """
    # 获取所有环境变量
    env = dict(os.environ)
    
    # 获取服务器配置，如果未设置则抛出错误
    server_config = env.get('MCP_SERVER_CONFIG')
    if not server_config:
        raise ValueError("MCP_SERVER_CONFIG environment variable is not set")
    
    try:
        # 解析配置字符串
        parts = shlex.split(server_config)
        if not parts:
            raise ValueError("Empty server config")
        command, args = parts[0], parts[1:]
    except Exception as e:
        raise ValueError(f"Failed to parse MCP_SERVER_CONFIG: {e}")
    
    # 添加一些有用的默认值
    env.setdefault('PYTHONUNBUFFERED', '1')
    env.setdefault('NODE_ENV', 'production')
    
    # 记录环境变量信息
    logger.info(f"Server command: {command}")
    logger.info(f"Server args: {args}")
    logger.info(f"Environment variables: {', '.join(f'{k}={v}' for k, v in env.items())}")
    return StdioServerParameters(
        command=command,
        args=args,
        env=env
    ) 