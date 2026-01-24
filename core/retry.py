"""
重试机制模块
提供统一的重试装饰器和工具函数
"""
import asyncio
import logging
from typing import TypeVar, Callable, Optional, List, Type
from functools import wraps
import time

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """重试配置"""
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 10.0,
        exponential_base: float = 2.0,
        retry_on: Optional[List[Type[Exception]]] = None
    ):
        """
        初始化重试配置
        
        Args:
            max_attempts: 最大重试次数
            initial_delay: 初始延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数退避基数
            retry_on: 需要重试的异常类型列表，None表示重试所有异常
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retry_on = retry_on or [Exception]


def retry_async(
    config: Optional[RetryConfig] = None,
    operation_name: Optional[str] = None
):
    """
    异步函数重试装饰器
    
    Args:
        config: 重试配置，默认使用RetryConfig()
        operation_name: 操作名称，用于日志记录
    
    Example:
        @retry_async(RetryConfig(max_attempts=3), "LLM调用")
        async def call_llm():
            ...
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            operation = operation_name or func.__name__
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(f"✅ {operation} 成功 (尝试 {attempt}/{config.max_attempts})")
                    return result
                except Exception as e:
                    last_exception = e
                    
                    # 检查是否需要重试此异常
                    should_retry = any(isinstance(e, exc_type) for exc_type in config.retry_on)
                    if not should_retry:
                        logger.error(f"❌ {operation} 失败，异常类型不在重试列表中: {type(e).__name__}")
                        raise
                    
                    if attempt < config.max_attempts:
                        # 计算延迟时间（指数退避）
                        delay = min(
                            config.initial_delay * (config.exponential_base ** (attempt - 1)),
                            config.max_delay
                        )
                        logger.warning(
                            f"⚠️ {operation} 失败 (尝试 {attempt}/{config.max_attempts}): {str(e)}，"
                            f"{delay:.2f}秒后重试..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"❌ {operation} 失败，已重试 {config.max_attempts} 次: {str(e)}")
            
            # 所有重试都失败，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator


def retry_sync(
    config: Optional[RetryConfig] = None,
    operation_name: Optional[str] = None
):
    """
    同步函数重试装饰器
    
    Args:
        config: 重试配置，默认使用RetryConfig()
        operation_name: 操作名称，用于日志记录
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            operation = operation_name or func.__name__
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(f"✅ {operation} 成功 (尝试 {attempt}/{config.max_attempts})")
                    return result
                except Exception as e:
                    last_exception = e
                    
                    # 检查是否需要重试此异常
                    should_retry = any(isinstance(e, exc_type) for exc_type in config.retry_on)
                    if not should_retry:
                        logger.error(f"❌ {operation} 失败，异常类型不在重试列表中: {type(e).__name__}")
                        raise
                    
                    if attempt < config.max_attempts:
                        # 计算延迟时间（指数退避）
                        delay = min(
                            config.initial_delay * (config.exponential_base ** (attempt - 1)),
                            config.max_delay
                        )
                        logger.warning(
                            f"⚠️ {operation} 失败 (尝试 {attempt}/{config.max_attempts}): {str(e)}，"
                            f"{delay:.2f}秒后重试..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"❌ {operation} 失败，已重试 {config.max_attempts} 次: {str(e)}")
            
            # 所有重试都失败，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator


async def with_timeout(
    coro: Callable[..., T],
    timeout: float,
    default_value: Optional[T] = None,
    operation_name: Optional[str] = None
) -> Optional[T]:
    """
    为异步操作添加超时控制
    
    Args:
        coro: 异步协程或可调用对象
        timeout: 超时时间（秒）
        default_value: 超时时的默认返回值
        operation_name: 操作名称，用于日志记录
    
    Returns:
        操作结果，如果超时则返回default_value
    """
    operation = operation_name or "操作"
    try:
        if asyncio.iscoroutine(coro):
            result = await asyncio.wait_for(coro, timeout=timeout)
        else:
            result = await asyncio.wait_for(coro(), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ {operation} 超时（{timeout}秒）")
        return default_value
    except Exception as e:
        logger.error(f"❌ {operation} 失败: {str(e)}")
        raise
