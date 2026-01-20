"""
LLM 服务模块
通过 Qianfan、OpenRouter 或 Sidecar 调用大语言模型

支持的模式：
- qianfan: 百度千帆
- openrouter: OpenRouter
- sidecar: 本地 Sidecar 服务

优化：添加重试机制和超时控制
"""
import logging
from time import time
from typing import Optional, AsyncGenerator, Tuple
from openai import AsyncOpenAI
from llm_utils.config import config
from core.retry import retry_async, RetryConfig, with_timeout
from core.exceptions import LLMError

logger = logging.getLogger(__name__)

# 获取LLM配置（支持Qianfan、OpenRouter和Sidecar）
llm_config = config.get_llm_config()

logger.info(f"Initializing LLM service in {llm_config['mode'].upper()} mode")
logger.info(f"  base_url: {llm_config['base_url']}")
logger.info(f"  model: {llm_config['model']}")

# 创建 OpenAI 客户端（兼容OpenRouter和Sidecar）
client = AsyncOpenAI(
    api_key=llm_config['api_key'],
    base_url=llm_config['base_url'],
)


class LLMService(object):
    """LLM 服务类"""

    def __init__(self):
        pass

    @staticmethod
    @retry_async(
        RetryConfig(
            max_attempts=3,
            initial_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0
        ),
        operation_name="LLM调用"
    )
    async def call_llm(
        model_name: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
        timeout: Optional[float] = None
    ) -> str:
        """
        调用 LLM（通过 Sidecar，带重试和超时控制）

        Args:
            model_name: 模型别名（如 qwen2-7b）
            messages: 消息列表，格式: [{"role": "user", "content": "..."}]
            temperature: 温度参数（0-1）
            max_tokens: 最大 token 数
            timeout: 超时时间（秒），None表示使用配置中的默认值

        Returns:
            模型响应文本

        Raises:
            LLMError: 调用失败时抛出异常
        """
        logger.info(f"Calling LLM: model={model_name}, messages={len(messages)}, temperature={temperature}")

        # 从配置获取超时时间
        if timeout is None:
            timeout = float(config.get("llm.timeout", 30.0))

        params = {
            'model': model_name,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens
        }

        try:
            t0 = time()
            
            # 使用超时控制
            async def _call():
                response = await client.chat.completions.create(**params)
                return response
            
            response = await with_timeout(
                _call(),
                timeout=timeout,
                operation_name=f"LLM调用({model_name})"
            )
            
            if response is None:
                raise LLMError("LLM调用超时", details={"model": model_name, "timeout": timeout})
            
            rt = time() - t0
            result = response.choices[0].message.content
            logger.info(f"LLM response received: rt={rt:.3f}s, length={len(result)}")
            return result

        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"LLM调用失败: {str(e)}", details={"model": model_name})

    @staticmethod
    async def call_llm_with_thinking(model_name, messages, temperature=0.7, max_tokens=500, enable_thinking=False):
        """
        调用 LLM 并提取思考内容（参考 test_llm_connection.py 实现）

        Args:
            model_name: 模型别名
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            enable_thinking: 是否启用思考模式（默认关闭，仅摘要生成时开启）

        Returns:
            (thinking_content, answer_content) 元组
            - thinking_content: 思考过程（如果模型支持且enable_thinking=True）
            - answer_content: 最终回答
        """
        import re
        
        logger.info(f"Calling LLM with thinking: model={model_name}, enable_thinking={enable_thinking}")

        params = {
            'model': model_name,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        
        # 可选：启用 thinking 模式（某些模型支持）
        # 从配置获取thinking预算
        thinking_config = config.get_thinking_config()
        if enable_thinking and thinking_config["enable_thinking"]:
            params['extra_body'] = {
                'enable_thinking': True,
                'thinking_budget': thinking_config["thinking_budget"]
            }
            logger.info(f"Thinking enabled with budget: {thinking_config['thinking_budget']}")

        try:
            t0 = time()
            response = await client.chat.completions.create(**params)
            rt = time() - t0

            message = response.choices[0].message
            thinking_content = None
            answer_content = message.content or ""
            
            # 方式1: 检查 reasoning_content 字段（Qwen3 格式）
            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                thinking_content = message.reasoning_content
                logger.info(f"Found reasoning_content: {len(thinking_content)} chars")
            
            # 方式2: 检查 thinking 字段
            if not thinking_content and hasattr(message, 'thinking') and message.thinking:
                thinking_content = message.thinking
                logger.info(f"Found thinking field: {len(thinking_content)} chars")
            
            # 方式3: 从响应内容中解析 <think>...</think> 标签
            if not thinking_content and answer_content:
                think_match = re.search(r'<think>(.*?)</think>', answer_content, re.DOTALL)
                if think_match:
                    thinking_content = think_match.group(1).strip()
                    # 移除思考标签后的内容作为答案
                    answer_content = re.sub(r'<think>.*?</think>\s*', '', answer_content, flags=re.DOTALL).strip()
                    logger.info(f"Extracted <think> tag: {len(thinking_content)} chars")
            
            logger.info(f"LLM response: rt={rt:.3f}s, thinking={len(thinking_content or '')}, answer={len(answer_content)}")
            return (thinking_content or "", answer_content)

        except Exception as e:
            logger.error(f"LLM call with thinking failed: {e}", exc_info=True)
            raise

    @staticmethod
    async def call_llm_stream(
        model_name: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
        enable_thinking: bool = False,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[Tuple[str, str], None]:
        """
        流式调用 LLM（token by token，带超时控制）
        
        参考 test_llm_connection.py 的 test_llm_think_stream 方法，
        支持检测 reasoning_content 和 thinking 字段。
        
        注意：enable_thinking 默认关闭，仅在摘要生成时显式开启。

        Args:
            model_name: 模型别名（如 qwen2-7b）
            messages: 消息列表，格式: [{"role": "user", "content": "..."}]
            temperature: 温度参数（0-1）
            max_tokens: 最大 token 数
            enable_thinking: 是否启用思考模式（默认关闭，仅摘要生成时开启）
            timeout: 超时时间（秒），None表示使用配置中的默认值

        Yields:
            (token_type, token_content) 元组
            - token_type: "thinking"、"content" 或 "done"
            - token_content: token 内容（"done" 时为空字符串）
            - "done" 表示流式响应已结束

        Raises:
            LLMError: 调用失败时抛出异常
        """
        logger.info(f"Calling LLM (stream): model={model_name}, messages={len(messages)}, enable_thinking={enable_thinking}")

        # 从配置获取超时时间（流式调用使用更长的超时）
        if timeout is None:
            timeout = float(config.get("llm.timeout", 30.0)) * 2  # 流式调用需要更长时间

        params = {
            'model': model_name,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'stream': True  # 启用流式
        }
        
        # 可选：启用 thinking 模式
        # 从配置获取thinking预算
        thinking_config = config.get_thinking_config()
        if enable_thinking and thinking_config["enable_thinking"]:
            params['extra_body'] = {
                'enable_thinking': True,
                'thinking_budget': thinking_config["thinking_budget"]
            }
            logger.info(f"Stream thinking enabled with budget: {thinking_config['thinking_budget']}")

        try:
            import inspect
            
            # 使用超时控制创建流
            async def _create_stream():
                create_result = client.chat.completions.create(**params)
                if inspect.iscoroutine(create_result):
                    return await create_result
                return create_result
            
            stream = await with_timeout(
                _create_stream(),
                timeout=timeout,
                operation_name=f"LLM流式调用({model_name})"
            )
            
            if stream is None:
                raise LLMError("LLM流式调用超时", details={"model": model_name, "timeout": timeout})
            
            async for chunk in stream:
                if not chunk.choices or len(chunk.choices) == 0:
                    continue
                    
                delta = chunk.choices[0].delta
                
                # 检查是否有思考内容（参考 test_llm_connection.py）
                reasoning = None
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    reasoning = delta.reasoning_content
                elif hasattr(delta, 'thinking') and delta.thinking:
                    reasoning = delta.thinking
                
                if reasoning:
                    yield ("thinking", reasoning)
                
                # 常规内容
                if delta.content:
                    yield ("content", delta.content)
            
            # 流式响应结束，发送明确的结束信号
            yield ("done", "")
                    
        except Exception as e:
            logger.error(f"LLM stream call failed: {e}", exc_info=True)
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"LLM流式调用失败: {str(e)}", details={"model": model_name})

    @staticmethod
    async def call_llm_with_fallback(model_name, messages, fallback_text=None, **kwargs):
        """
        调用 LLM，支持降级策略

        Args:
            model_name: 模型别名
            messages: 消息列表
            fallback_text: 降级时返回的文本
            **kwargs: 其他参数传递给 call_llm

        Returns:
            模型响应文本，失败时返回降级文本
        """
        try:
            return await LLMService.call_llm(model_name, messages, **kwargs)
        except Exception as e:
            logger.warning(f"LLM call failed, using fallback: {e}")
            if fallback_text:
                return fallback_text
            return "服务暂时不可用，请稍后重试"
