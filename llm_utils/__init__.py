"""
NLU Server 模块
提供配置管理和 LLM 服务
"""
from llm_utils.config import config
from llm_utils.llm_service import LLMService

__all__ = ['config', 'LLMService']
