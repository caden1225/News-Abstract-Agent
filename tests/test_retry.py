"""
重试机制单元测试
"""
import pytest
import asyncio
from core.retry import retry_async, RetryConfig, with_timeout
from core.exceptions import LLMError


@pytest.mark.asyncio
async def test_retry_success():
    """测试重试成功的情况"""
    call_count = 0
    
    @retry_async(RetryConfig(max_attempts=3), "测试操作")
    async def test_func():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result = await test_func()
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_with_failure():
    """测试重试失败后成功的情况"""
    call_count = 0
    
    @retry_async(RetryConfig(max_attempts=3, initial_delay=0.1), "测试操作")
    async def test_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise Exception("临时失败")
        return "success"
    
    result = await test_func()
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_max_attempts():
    """测试达到最大重试次数"""
    call_count = 0
    
    @retry_async(RetryConfig(max_attempts=3, initial_delay=0.1), "测试操作")
    async def test_func():
        nonlocal call_count
        call_count += 1
        raise Exception("总是失败")
    
    with pytest.raises(Exception):
        await test_func()
    
    assert call_count == 3


@pytest.mark.asyncio
async def test_with_timeout_success():
    """测试超时控制成功的情况"""
    async def slow_operation():
        await asyncio.sleep(0.1)
        return "success"
    
    result = await with_timeout(slow_operation(), timeout=1.0)
    assert result == "success"


@pytest.mark.asyncio
async def test_with_timeout_failure():
    """测试超时控制失败的情况"""
    async def slow_operation():
        await asyncio.sleep(2.0)
        return "success"
    
    result = await with_timeout(slow_operation(), timeout=0.5, default_value="timeout")
    assert result == "timeout"
