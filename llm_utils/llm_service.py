"""
LLM 服务模块
通过 Sidecar 调用大语言模型
"""
import logging
from time import time
from openai import AsyncOpenAI
from llm_utils.config import config

logger = logging.getLogger(__name__)

# 从配置读取 Sidecar 地址和密钥
api_key = config.get_value("llm.api_key")
base_url = config.get_value("llm.base_url")

if not api_key:
    logger.warning("LLM API key not configured, using default")
    api_key = "zbx:..."

if not base_url:
    logger.error("LLM base_url not configured")
    raise ValueError("llm.base_url must be configured in config.yaml")

logger.info(f"Initializing LLM service with base_url: {base_url}")

# 创建 OpenAI 客户端（连接到 Sidecar）
client = AsyncOpenAI(
    api_key=api_key,
    base_url=base_url,
)


class LLMService(object):
    """LLM 服务类"""

    def __init__(self):
        pass

    @staticmethod
    async def call_llm(model_name, messages, temperature=0.7, max_tokens=500):
        """
        调用 LLM（通过 Sidecar）

        Args:
            model_name: 模型别名（如 qwen2-7b）
            messages: 消息列表，格式: [{"role": "user", "content": "..."}]
            temperature: 温度参数（0-1）
            max_tokens: 最大 token 数

        Returns:
            模型响应文本

        Raises:
            Exception: 调用失败时抛出异常
        """
        logger.info(f"Calling LLM: model={model_name}, messages={len(messages)}, temperature={temperature}")

        params = {
            'model': model_name,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens
        }

        try:
            t0 = time()
            response = await client.chat.completions.create(**params)
            rt = time() - t0

            result = response.choices[0].message.content
            logger.info(f"LLM response received: rt={rt:.3f}s, length={len(result)}")
            return result

        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise

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
