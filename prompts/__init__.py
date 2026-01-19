"""
统一 Prompt 管理模块

使用外部文件管理 prompt 模板，使用 str.format() 进行占位符替换
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 导入 PromptManager 和工具函数
from .manager import (
    PromptManager,
    get_prompt_manager,
    clean_news_text,
    format_news_items,
    build_news_summary_messages,
    build_intent_analysis_prompt,
)

# 导出所有公共接口
__all__ = [
    # 主要类
    "PromptManager",

    # 便捷函数
    "get_prompt_manager",
    "build_news_summary_messages",
    "build_intent_analysis_prompt",

    # 工具函数
    "clean_news_text",
    "format_news_items",
]
