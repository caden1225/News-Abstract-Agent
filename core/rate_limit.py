"""
API速率限制模块
提供统一的速率限制功能
"""
import logging
from typing import Optional, Callable
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

# 创建速率限制器
limiter = Limiter(key_func=get_remote_address)


def get_rate_limit_key(request: Request) -> str:
    """
    获取速率限制的键（基于IP地址）
    
    Args:
        request: FastAPI请求对象
    
    Returns:
        速率限制键（IP地址）
    """
    # 优先使用X-Forwarded-For头（如果存在代理）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # 取第一个IP（客户端真实IP）
        client_ip = forwarded_for.split(",")[0].strip()
        return client_ip
    
    # 回退到直接IP
    return get_remote_address(request)


# 更新速率限制器的key函数
limiter.key_func = get_rate_limit_key


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    速率限制超出时的处理函数
    
    Args:
        request: FastAPI请求对象
        exc: RateLimitExceeded异常
    
    Returns:
        HTTPException响应
    """
    logger.warning(
        f"速率限制超出: IP={get_rate_limit_key(request)}, "
        f"limit={exc.detail.get('limit', 'unknown')}"
    )
    raise HTTPException(
        status_code=429,
        detail={
            "error": "请求过于频繁，请稍后再试",
            "retry_after": exc.detail.get("retry_after", 60),
            "limit": exc.detail.get("limit", "unknown")
        }
    )


# 注册全局异常处理器
_rate_limit_exceeded_handler = rate_limit_exceeded_handler


def create_rate_limit_decorator(
    default_limit: str = "10/minute",
    per_endpoint: bool = True
) -> Callable:
    """
    创建速率限制装饰器
    
    Args:
        default_limit: 默认限制（如 "10/minute", "100/hour"）
        per_endpoint: 是否按端点分别限制（True）或全局限制（False）
    
    Returns:
        速率限制装饰器
    """
    def decorator(limit: Optional[str] = None):
        """
        速率限制装饰器
        
        Args:
            limit: 限制字符串（如 "10/minute"），None使用default_limit
        
        Example:
            @app.post("/api/v1/chat")
            @create_rate_limit_decorator("5/minute")(limit="5/minute")
            async def chat():
                ...
        """
        actual_limit = limit or default_limit
        
        def wrapper(func):
            # 使用limiter装饰函数
            return limiter.limit(actual_limit)(func)
        
        return wrapper
    
    return decorator


# 预定义的速率限制装饰器
rate_limit_default = create_rate_limit_decorator("10/minute")
rate_limit_strict = create_rate_limit_decorator("5/minute")
rate_limit_loose = create_rate_limit_decorator("30/minute")
