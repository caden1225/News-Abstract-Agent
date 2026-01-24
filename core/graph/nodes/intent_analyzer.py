"""
意图分析节点模块

包含：
1. 底层工具函数：规则分析、LLM分析
2. LangGraph节点函数：编排并行分析
"""
import logging
import json
import asyncio
import time
from typing import Dict, Any
from datetime import date, timedelta

from prompts import build_intent_analysis_prompt
from core.constants import LANGUAGE_CONFIG, LLM_CONFIG, WORKFLOW_CONFIG
from core.task_manager import get_language_task_manager
from models.state import NewsAgentState

logger = logging.getLogger(__name__)


def detect_language_by_semantics(query: str) -> tuple[str, float]:
    """
    基于语义的语言判断（优先识别用户明确的语言要求）

    Args:
        query: 用户查询文本

    Returns:
        (language, confidence): ("zh"|"en"|"ko", 0.0-1.0)
    """
    if not query:
        return (LANGUAGE_CONFIG.DEFAULT_LANGUAGE, LANGUAGE_CONFIG.DEFAULT_CONFIDENCE)

    query_lower = query.lower()
    
    # 优先级1：检查用户明确的语言要求（语义优先）
    # 韩语相关表达
    korean_keywords = [
        "使用韩语", "用韩语", "韩语播报", "韩语", "한국어", "한국어로",
        "korean", "in korean", "use korean", "korean please"
    ]
    for keyword in korean_keywords:
        if keyword in query_lower or keyword in query:
            return ("ko", 0.95)
    
    # 英语相关表达
    english_keywords = [
        "使用英语", "用英语", "英语播报", "英文播报", "用英文", "使用英文",
        "english", "in english", "use english", "english please"
    ]
    for keyword in english_keywords:
        if keyword in query_lower:
            return ("en", 0.95)
    
    # 中文相关表达
    chinese_keywords = [
        "使用中文", "用中文", "中文播报", "中文", "chinese", "in chinese"
    ]
    for keyword in chinese_keywords:
        if keyword in query_lower:
            return ("zh", 0.95)
    
    # 优先级2：如果没有明确的语言要求，根据查询文本的语言特征判断
    return detect_language_by_rules(query)


def detect_language_by_rules(query: str) -> tuple[str, float]:
    """
    基于规则的快速语言判断（根据查询文本的语言特征）

    Args:
        query: 用户查询文本

    Returns:
        (language, confidence): ("zh"|"en"|"ko", 0.0-1.0)
    """
    if not query:
        return (LANGUAGE_CONFIG.DEFAULT_LANGUAGE, LANGUAGE_CONFIG.DEFAULT_CONFIDENCE)

    # 1. 检查韩文字符 (가-힣, Unicode范围: AC00-D7A3)
    korean_chars = len([c for c in query if '\uAC00' <= c <= '\uD7A3'])
    korean_ratio = korean_chars / len(query) if query else 0
    if korean_ratio > LANGUAGE_CONFIG.KOREAN_RATIO_THRESHOLD:
        return ("ko", LANGUAGE_CONFIG.KOREAN_CONFIDENCE)

    # 2. 检查中文字符 (\u4e00-\u9fff)
    chinese_chars = len([c for c in query if '\u4e00' <= c <= '\u9fff'])
    chinese_ratio = chinese_chars / len(query) if query else 0
    if chinese_ratio > LANGUAGE_CONFIG.CHINESE_RATIO_THRESHOLD:
        return ("zh", LANGUAGE_CONFIG.CHINESE_CONFIDENCE_HIGH)

    # 3. 检查英文字符（ASCII字母）
    english_chars = len([c for c in query if c.isalpha() and ord(c) < 128])
    english_ratio = english_chars / len(query) if query else 0
    if english_ratio > LANGUAGE_CONFIG.ENGLISH_RATIO_THRESHOLD:
        return ("en", LANGUAGE_CONFIG.ENGLISH_CONFIDENCE)

    # 4. 混合情况：如果中文字符占比较高，判断为中文
    if chinese_ratio > LANGUAGE_CONFIG.CHINESE_RATIO_LOW_THRESHOLD:
        return ("zh", LANGUAGE_CONFIG.CHINESE_CONFIDENCE_MEDIUM)

    # 5. 默认中文
    return ("zh", LANGUAGE_CONFIG.CHINESE_CONFIDENCE_DEFAULT)


def analyze_intent_by_rules(query: str) -> Dict[str, Any]:
    """
    基于规则的快速意图分析（包含语言判断）

    支持爬虫数据库的分类：hot_news, today_focus

    Args:
        query: 用户查询文本

    Returns:
        意图分析结果字典
    """
    query_lower = query.lower()

    # 语言判断（优先语义，其次规则）
    summary_target_language, language_confidence = detect_language_by_semantics(query)

    # 默认值
    result = {
        "query_type": "general_news",
        "target_date": date.today().isoformat(),
        "category": None,
        "search_keywords": [],
        "search_strategy": "by_date_only",
        "data_source": "cache",
        "summary_target_language": summary_target_language,
        "tts_language": summary_target_language,
        "language_confidence": language_confidence
    }

    # 1. 判断时间
    if any(kw in query for kw in ["今天", "今日", "最新", "当前"]):
        result["query_type"] = "general_news"
        result["target_date"] = date.today().isoformat()
        result["data_source"] = "cache"

    elif any(kw in query for kw in ["昨天", "昨日"]):
        result["query_type"] = "daily_news"
        result["target_date"] = (date.today() - timedelta(days=1)).isoformat()
        result["data_source"] = "cache"

    elif any(kw in query for kw in ["前天"]):
        result["query_type"] = "daily_news"
        result["target_date"] = (date.today() - timedelta(days=2)).isoformat()
        result["data_source"] = "cache"

    # 2. 判断分类（支持爬虫数据库的分类）
    category_keywords = {
        "hot_news": ["热点", "热门", "热搜", "trending",
                     "科技", "ai", "人工智能", "芯片", "互联网", "5g",
                     "财经", "股市", "经济", "金融", "股票", "a股",
                     "体育", "足球", "篮球", "nba", "奥运", "国足",
                     "娱乐", "电影", "明星", "音乐"],
        "today_focus": ["焦点", "关注", "重点", "focus"]
    }

    for category, keywords in category_keywords.items():
        if any(kw in query_lower for kw in keywords):
            result["category"] = category
            result["query_type"] = "category_news"
            break

    return result


async def analyze_intent_with_llm(
    query: str,
    include_language: bool = True
) -> Dict[str, Any]:
    """
    使用 LLM 进行意图分析

    通过 LLM 提取查询的：
    - query_type: 查询类型
    - target_date: 目标日期
    - category: 新闻分类
    - search_keywords: 搜索关键词
    - search_strategy: 检索策略
    - tts_language: TTS语言（可选）
    - language_confidence: 语言判断置信度（可选）

    Args:
        query: 用户查询
        include_language: 是否包含语言判断字段

    Returns:
        包含意图分析结果的字典
    """
    from llm_utils.llm_service import LLMService, llm_config

    try:
        # 构建提示词（使用统一的 prompt 管理系统）
        prompt = build_intent_analysis_prompt(query)

        # 获取模型名称
        model_name = llm_config['model']

        logger.info("调用LLM进行意图分析: mode=%s, model=%s, query=%s..., include_language=%s",
                   llm_config['mode'], model_name, query[:50], include_language)

        # 调用LLM，要求JSON格式输出
        # 注意：意图分析不启用thinking，使用普通call_llm
        response = await LLMService.call_llm(
            model_name=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "你是意图分析专家。请严格按照JSON格式输出分析结果，不要包含任何额外文字。"
                },
                {"role": "user", "content": prompt}
            ],
            temperature=LLM_CONFIG.INTENT_TEMPERATURE,
            max_tokens=LLM_CONFIG.INTENT_MAX_TOKENS
        )

        # 解析 JSON 响应
        # 清理可能的 markdown 代码块标记
        response_cleaned = response.strip()
        if response_cleaned.startswith("```json"):
            response_cleaned = response_cleaned[7:]
        elif response_cleaned.startswith("```"):
            response_cleaned = response_cleaned[3:]
        if response_cleaned.endswith("```"):
            response_cleaned = response_cleaned[:-3]
        response_cleaned = response_cleaned.strip()

        # 解析 JSON
        result = json.loads(response_cleaned)

        # 标准化字段名
        standardized = {
            "query_type": result.get("query_type", "general_news"),
            "target_date": result.get("target_date"),
            "category": result.get("category"),
            "search_keywords": result.get("search_keywords", []),
            "search_strategy": result.get("search_strategy", "by_date_only"),
        }

        # 可选的语言判断字段
        if include_language:
            # 优先使用summary_target_language，如果没有则使用tts_language（向后兼容）
            target_lang = result.get("summary_target_language") or result.get("tts_language", "zh")
            standardized.update({
                "summary_target_language": target_lang,
                "tts_language": target_lang,  # 保持向后兼容
                "language_confidence": result.get("language_confidence", 0.8),
            })

        logger.info("LLM意图分析成功: query_type=%s, target_date=%s, category=%s, keywords=%s, summary_target_language=%s",
                   standardized['query_type'], standardized['target_date'],
                   standardized['category'], standardized['search_keywords'],
                   standardized.get('summary_target_language', standardized.get('tts_language', 'N/A')))

        return standardized

    except json.JSONDecodeError as e:
        logger.error("LLM意图分析JSON解析失败: %s, response=%s", e, response[:200])
        # 降级到规则分析
        logger.info("降级到规则分析")
        return analyze_intent_by_rules(query)
    except Exception as e:
        logger.error("LLM意图分析失败: %s，降级到规则分析", e)
        # 降级到规则分析
        return analyze_intent_by_rules(query)


# ==================== LangGraph节点函数 ====================

async def intent_analyzer_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    意图分析节点（LangGraph节点）

    并行执行规则分析和LLM分析，哪个先返回就用哪个
    规则命中时保留LLM任务用于语言判断

    Args:
        state: NewsAgentState 状态对象

    Returns:
        更新的状态字典
    """
    query = state["query"]
    request_id = state.get("request_id", "")

    # 打印节点开始
    print("\n" + "🔍" * 20)
    print("  节点 1: 意图分析 (并行: 规则 + LLM)")
    print("🔍" * 20)

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - query: {query}")
    print(f"  - request_id: {request_id}")

    start = time.time()

    # 并行执行规则分析和LLM分析
    # 规则分析是同步函数，使用 asyncio.to_thread 包装
    rules_task = asyncio.create_task(
        asyncio.to_thread(analyze_intent_by_rules, query)
    )
    llm_task = asyncio.create_task(analyze_intent_with_llm_and_language(query))

    # 等待第一个完成的任务
    done, pending = await asyncio.wait(
        [rules_task, llm_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    # 获取第一个完成的结果
    completed_task = done.pop()
    result = await completed_task
    method_used = "规则" if completed_task == rules_task else "LLM"

    llm_language_pending = False
    llm_language_ready = False

    # 判断是否使用规则结果（基于置信度）
    if completed_task == rules_task:
        # 规则分析完成，检查置信度
        confidence = result.get("language_confidence", 0.0)

        # 检查规则意图识别的置信度
        if confidence >= WORKFLOW_CONFIG.RULE_CONFIDENCE_THRESHOLD:
            # 规则命中：使用规则的意图识别结果
            # 但保留LLM任务继续执行（用于语言判断）

            # 将LLM任务存储到全局管理器
            task_manager = get_language_task_manager()
            await task_manager.store_task(request_id, llm_task)

            # 设置标志：LLM语言判断还在执行中
            llm_language_pending = True
            llm_language_ready = False

            method_used = "规则（提前执行，LLM语言判断异步进行）"

            # 注意：不取消LLM任务，让它继续执行
        else:
            # 规则置信度低，等待LLM结果
            logger.info("规则分析置信度较低 (%.2f)，等待LLM结果...", confidence)
            llm_result = await llm_task
            result = llm_result
            llm_language_pending = False
            llm_language_ready = True
            method_used = "LLM（规则置信度低）"
    else:
        # LLM先完成，取消规则任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        llm_language_pending = False
        llm_language_ready = True
        method_used = "LLM"

    elapsed = (time.time() - start) * 1000

    # 打印分析结果（安全访问字段）
    print(f"\n📊 {method_used} 分析结果 (耗时: {elapsed:.2f}ms):")
    print(f"  - 查询类型 (query_type): {result.get('query_type', 'N/A')}")
    print(f"  - 目标日期 (target_date): {result.get('target_date', 'N/A')}")
    print(f"  - 新闻分类 (category): {result.get('category', 'N/A')}")
    print(f"  - 搜索关键词 (keywords): {result.get('search_keywords', [])}")
    print(f"  - 检索策略 (strategy): {result.get('search_strategy', 'N/A')}")
    summary_lang = result.get('summary_target_language') or result.get('tts_language', 'zh')
    print(f"  - 摘要目标语言 (summary_target_language): {summary_lang}")
    print(f"  - 语言置信度 (confidence): {result.get('language_confidence', 0.5):.2f}")

    # 根据检索策略决定数据来源
    search_strategy = result.get("search_strategy", "by_date_only")
    if search_strategy == "by_keyword":
        data_source = "keyword_search"
    elif "by_date" in search_strategy:
        data_source = "cache"
    else:
        data_source = "cache"

    query_type = result.get("query_type") or "general_news"

    # 构建返回状态
    update = {
        "query_type": query_type,
        "search_keywords": result.get("search_keywords", []),
        "search_strategy": search_strategy,
        "target_date": result.get("target_date"),
        "category": result.get("category"),
        "data_source": data_source,

        # 摘要目标语言配置（优先使用summary_target_language）
        "summary_target_language": result.get("summary_target_language") or result.get("tts_language", "zh"),
        "tts_language": result.get("summary_target_language") or result.get("tts_language", "zh"),  # 保持向后兼容
        "language_confidence": result.get("language_confidence", 0.5),

        # LLM语言判断任务状态
        "llm_language_pending": llm_language_pending,
        "llm_language_ready": llm_language_ready,

        # 进度更新
        "current_step": "正在分析您的查询...",
        "progress_percentage": WORKFLOW_CONFIG.PROGRESS_INTENT_ANALYSIS,
        "processing_steps": [f"🔍 意图识别：{method_used}分析完成（目标语言: {summary_lang}）"]
    }

    logger.info("✅ 意图分析完成 (方法: %s): query_type=%s, data_source=%s, elapsed=%.2fms",
               method_used, query_type, data_source, elapsed)
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms (使用: {method_used})")

    return update


# 辅助函数：带语言判断的LLM意图分析
async def analyze_intent_with_llm_and_language(query: str) -> Dict[str, Any]:
    """
    使用LLM进行意图分析（包含语言判断）
    这是意图分析节点的辅助函数

    Args:
        query: 用户查询

    Returns:
        意图分析结果
    """
    return await analyze_intent_with_llm(query, include_language=True)
