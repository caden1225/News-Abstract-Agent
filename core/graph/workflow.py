"""
LangGraph工作流构建
"""
from langgraph.graph import StateGraph, END

from models.state import NewsAgentState
from core.graph.nodes import (
    intent_analyzer_node,
    cache_query_node,  # 重命名：cache_checker_node -> cache_query_node
    fetch_data_node,   # 新增：统一处理关键词搜索和在线获取
    news_selector_node,
    summarizer_node,
    tts_generator_node,
    response_builder_node
)
import logging

logger = logging.getLogger(__name__)


# ==================== 条件边函数 ====================

def decide_data_source(state: NewsAgentState) -> str:
    """
    决定数据来源（基于 LLM 意图分析结果）
    
    Returns:
        "cache" - 使用缓存
        "fetch" - 获取数据（关键词搜索或在线获取）
    """
    # 优先使用新的 query_type 字段
    query_type = state.get("query_type", "")
    intent_type = state.get("intent_type", "")  # 兼容旧字段
    
    logger.info(f"数据源决策: query_type={query_type}, intent_type={intent_type}")
    
    # 关键词搜索或指定日期查询 -> 获取数据
    if (query_type == "keyword_search" or 
        query_type == "daily_news" or 
        intent_type == "keyword_search" or 
        intent_type == "specific_date"):
        return "fetch"
    
    # 其他情况 -> 检查缓存
    return "cache"


def decide_after_cache(state: NewsAgentState) -> str:
    """
    缓存检查后的决策
    
    Returns:
        "use_cached" - 使用缓存数据
        "fetch" - 获取数据
    """
    cache_hit = state.get("cache_hit", False)
    
    logger.info(f"缓存检查决策: cache_hit={cache_hit}")
    
    if cache_hit:
        return "use_cached"
    else:
        return "fetch"


def should_continue(state: NewsAgentState) -> str:
    """
    判断是否继续处理

    Returns:
        "continue" - 继续
        "error" - 有错误，结束
    """
    error = state.get("error")

    if error:
        logger.error(f"检测到错误: {error}")
        return "error"
    else:
        return "continue"


# ==================== 工作流构建 ====================

def build_news_workflow() -> StateGraph:
    """
    构建完整的新闻Agent工作流（用于非流式模式）

    Returns:
        编译后的StateGraph
    """
    logger.info("构建新闻Agent工作流...")

    # 创建工作流
    workflow = StateGraph(NewsAgentState)

    # ==================== 添加节点 ====================

    workflow.add_node("intent_analyzer", intent_analyzer_node)
    workflow.add_node("cache_query", cache_query_node)  # 重命名
    workflow.add_node("fetch_data", fetch_data_node)   # 新增
    workflow.add_node("news_selector", news_selector_node)
    workflow.add_node("summarizer", summarizer_node)
    workflow.add_node("tts_generator", tts_generator_node)
    workflow.add_node("response_builder", response_builder_node)

    # ==================== 设置入口 ====================

    workflow.set_entry_point("intent_analyzer")

    # ==================== 添加边 ====================

    # 1. 意图分析 -> 数据源决策
    workflow.add_conditional_edges(
        "intent_analyzer",
        decide_data_source,
        {
            "cache": "cache_query",
            "fetch": "fetch_data"
        }
    )

    # 2. 缓存检查 -> 决策
    workflow.add_conditional_edges(
        "cache_query",
        decide_after_cache,
        {
            "use_cached": "news_selector",
            "fetch": "fetch_data"
        }
    )

    # 3. 数据获取 -> 新闻选择
    workflow.add_edge("fetch_data", "news_selector")

    # 4. 新闻选择 -> 摘要生成（先生成文本）
    workflow.add_conditional_edges(
        "news_selector",
        should_continue,
        {
            "continue": "summarizer",  # 先生成文本
            "error": "response_builder"
        }
    )

    # 5. 摘要生成 -> TTS生成（用文本生成音频）
    # 注意：必须先完成文本生成，然后才能合成对应的音频
    workflow.add_edge("summarizer", "tts_generator")
    
    # 6. TTS生成 -> 响应构建
    workflow.add_edge("tts_generator", "response_builder")

    # 7. 响应构建 -> 结束
    workflow.add_edge("response_builder", END)

    # ==================== 编译工作流 ====================

    compiled_workflow = workflow.compile()

    logger.info("工作流构建完成")

    return compiled_workflow


def build_preprocessing_workflow() -> StateGraph:
    """
    构建前置处理工作流（用于流式模式）
    
    仅包含：意图分析 -> 缓存/获取 -> 新闻选择
    流式生成（摘要 + TTS）由 orchestrator 手动处理
    
    Returns:
        编译后的StateGraph
    """
    logger.info("构建前置处理工作流（用于流式模式）...")

    # 创建工作流
    workflow = StateGraph(NewsAgentState)

    # ==================== 添加前置节点 ====================

    workflow.add_node("intent_analyzer", intent_analyzer_node)
    workflow.add_node("cache_query", cache_query_node)
    workflow.add_node("fetch_data", fetch_data_node)
    workflow.add_node("news_selector", news_selector_node)

    # ==================== 设置入口 ====================

    workflow.set_entry_point("intent_analyzer")

    # ==================== 添加边 ====================

    # 1. 意图分析 -> 数据源决策
    workflow.add_conditional_edges(
        "intent_analyzer",
        decide_data_source,
        {
            "cache": "cache_query",
            "fetch": "fetch_data"
        }
    )

    # 2. 缓存检查 -> 决策
    workflow.add_conditional_edges(
        "cache_query",
        decide_after_cache,
        {
            "use_cached": "news_selector",
            "fetch": "fetch_data"
        }
    )

    # 3. 数据获取 -> 新闻选择
    workflow.add_edge("fetch_data", "news_selector")

    # 4. 新闻选择 -> 结束（流式生成由 orchestrator 手动处理）
    workflow.add_edge("news_selector", END)

    # ==================== 编译工作流 ====================

    compiled_workflow = workflow.compile()

    logger.info("前置处理工作流构建完成")

    return compiled_workflow


# ==================== 测试代码 ====================

# if __name__ == "__main__":
#     import asyncio
#     from datetime import date

#     async def test_workflow():
#         """测试工作流"""
#         logging.basicConfig(
#             level=logging.INFO,
#             format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#         )

#         # 构建工作流
#         workflow = build_news_workflow()

#         # 初始状态
#         initial_state: NewsAgentState = {
#             "query": "今天有什么新闻",
#             "request_id": "test_001",
#             "stream": True,
#             # 新字段 (LLM提取)
#             "query_type": "",
#             "search_keywords": [],
#             "search_strategy": "",
#             "intent_reasoning": None,
#             # 兼容旧字段
#             "intent_type": "",
#             "keywords": [],
#             "target_date": None,
#             "category": None,
#             "data_source": "",
#             "cache_hit": False,
#             "news_list": [],
#             "news_count": 0,
#             "selected_news": [],
#             "summary": "",
#             "audio_data": None,
#             "processing_steps": [],
#             "current_step": "",
#             "progress_percentage": 0,
#             "image_links": [],
#             "error": None,
#             "completed": False
#         }

#         # 执行工作流
#         print("\n" + "=" * 70)
#         print("开始执行工作流")
#         print("=" * 70 + "\n")

#         result = await workflow.ainvoke(initial_state)

#         print("\n" + "=" * 70)
#         print("工作流执行完成")
#         print("=" * 70)
#         print(f"\n处理步骤:")
#         for step in result.get("processing_steps", []):
#             print(f"  - {step}")

#         print(f"\n最终状态:")
#         print(f"  新闻数量: {result.get('news_count', 0)}")
#         print(f"  图片数量: {len(result.get('image_links', []))}")
#         print(f"  摘要长度: {len(result.get('summary', ''))}")
#         print(f"  音频数据: {'有' if result.get('audio_data') else '无'}")
#         print(f"  完成: {result.get('completed', False)}")

#         if result.get("error"):
#             print(f"\n⚠️ 错误: {result['error']}")

#     # 运行测试
#     asyncio.run(test_workflow())
