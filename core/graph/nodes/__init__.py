"""
LangGraph节点模块 - 导出接口

此模块负责导出所有LangGraph节点函数，节点实现分布在各个子模块中：

模块结构:
- intent_analyzer: 意图分析节点（包含工具函数和节点函数）
- data_fetcher: 数据获取节点
- content_generator: 内容生成节点
- response_builder: 响应构建节点
"""

# 从各个子模块导入节点函数
from .intent_analyzer import (
    # 工具函数
    detect_language_by_rules,
    analyze_intent_by_rules,
    analyze_intent_with_llm,
    analyze_intent_with_llm_and_language,
    # 节点函数
    intent_analyzer_node,
)

from .data_fetcher import (
    cache_query_node,
    fetch_data_node,
)

from .content_generator import (
    news_selector_node,
    summarizer_node,
    build_summary_messages,
    generate_summary_with_llm,
    parse_thinking_and_summary,
    generate_simple_summary,
)

from .response_builder import (
    tts_generator_node,
    parallel_start_node,
    parallel_join_node,
    response_builder_node,
)

__all__ = [
    # 意图分析
    "intent_analyzer_node",
    "detect_language_by_rules",
    "analyze_intent_by_rules",
    "analyze_intent_with_llm",
    "analyze_intent_with_llm_and_language",

    # 数据获取
    "cache_query_node",
    "fetch_data_node",

    # 内容生成
    "news_selector_node",
    "summarizer_node",
    "build_summary_messages",
    "generate_summary_with_llm",
    "parse_thinking_and_summary",
    "generate_simple_summary",

    # 响应构建
    "tts_generator_node",
    "parallel_start_node",
    "parallel_join_node",
    "response_builder_node",
]
