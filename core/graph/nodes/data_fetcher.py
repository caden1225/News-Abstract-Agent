"""
数据获取节点

包含缓存查询和数据获取功能
"""
import logging
import time
from typing import Dict, Any
from datetime import date

from core.crawler_service import get_crawler_service
from core.constants import DATABASE_CONFIG, WORKFLOW_CONFIG
from models.state import NewsAgentState

logger = logging.getLogger(__name__)


async def cache_query_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    缓存查询节点
    检查数据库是否有缓存数据
    """
    query_type = state.get("query_type", "")
    target_date = state.get("target_date", date.today().isoformat())
    category = state.get("category")

    # 打印节点开始
    print("\n" + "💾" * 20)
    print("  节点 2: 缓存查询")
    print("💾" * 20)

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - query_type: {query_type}")
    print(f"  - target_date: {target_date}")
    print(f"  - category: {category}")

    # 查询爬虫数据库
    print(f"\n🔍 查询数据库...")
    start = time.time()

    crawler = get_crawler_service()
    cached_news = crawler.get_news_by_date(target_date, category)

    elapsed = (time.time() - start) * 1000

    cache_hit = len(cached_news) > 0

    # 打印查询结果
    print(f"\n📊 查询结果:")
    print(f"  - 缓存命中: {'✅ 是' if cache_hit else '❌ 否'}")
    print(f"  - 新闻数量: {len(cached_news)}")
    print(f"  - 查询耗时: {elapsed:.2f}ms")

    if cache_hit and cached_news:
        print(f"\n📰 找到的新闻:")
        for i, news in enumerate(cached_news[:3], 1):
            title = news.get("title", "")
            print(f"  {i}. {title[:60]}...")
        if len(cached_news) > 3:
            print(f"  ... 还有 {len(cached_news) - 3} 条")

    update = {
        "cache_hit": cache_hit,
        "news_list": cached_news if cache_hit else [],
        "news_count": len(cached_news) if cache_hit else 0,
        "current_step": "正在检查新闻缓存...",
        "progress_percentage": WORKFLOW_CONFIG.PROGRESS_CACHE_QUERY,
        "processing_steps": [
            f"💾 检查爬虫数据库: {target_date}",
            f"{'✅ 找到' if cache_hit else '❌ 未找到'} {len(cached_news)} 条缓存新闻"
        ]
    }

    logger.info(f"✅ 缓存检查完成: hit={cache_hit}, count={len(cached_news)}, elapsed={elapsed:.2f}ms")
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")

    return update


async def fetch_data_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    数据获取节点（统一处理关键词搜索和在线获取）
    根据 query_type 决定使用关键词搜索还是在线获取
    """
    query_type = state.get("query_type", "")
    search_keywords = state.get("search_keywords", [])
    target_date = state.get("target_date")
    category = state.get("category")

    # 打印节点开始
    print("\n" + "📥" * 20)
    print("  节点 3: 数据获取")
    print("📥" * 20)

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - query_type: {query_type}")
    print(f"  - search_keywords: {search_keywords}")
    print(f"  - target_date: {target_date}")
    print(f"  - category: {category}")

    start = time.time()

    crawler = get_crawler_service()
    news_list = []

    # 根据 query_type 决定获取方式
    if query_type == "keyword_search" and search_keywords:
        # 关键词搜索
        print(f"\n🔍 使用关键词搜索: {', '.join(search_keywords)}")
        news_list = crawler.get_news_by_keywords(
            search_keywords,
            limit=DATABASE_CONFIG.KEYWORD_SEARCH_LIMIT
        )
    else:
        # 在线获取（按日期和分类）
        print(f"\n📰 在线获取新闻: date={target_date}, category={category}")
        if target_date:
            # get_news_by_date 方法支持 category 参数
            news_list = crawler.get_news_by_date(target_date, category=category)
            # 限制数量
            if len(news_list) > DATABASE_CONFIG.CACHE_NEWS_LIMIT:
                news_list = news_list[:DATABASE_CONFIG.CACHE_NEWS_LIMIT]
        else:
            # 默认获取今日新闻
            today = date.today().isoformat()
            news_list = crawler.get_news_by_date(today, category=category)
            # 限制数量
            if len(news_list) > DATABASE_CONFIG.CACHE_NEWS_LIMIT:
                news_list = news_list[:DATABASE_CONFIG.CACHE_NEWS_LIMIT]

    elapsed = (time.time() - start) * 1000

    # 打印获取结果
    print(f"\n📊 获取结果:")
    print(f"  - 新闻数量: {len(news_list)} 条")
    print(f"  - 获取耗时: {elapsed:.2f}ms")

    if news_list:
        print(f"\n📰 找到的新闻:")
        for i, news in enumerate(news_list[:3], 1):
            title = news.get("title", "")
            print(f"  {i}. {title[:60]}...")
        if len(news_list) > 3:
            print(f"  ... 还有 {len(news_list) - 3} 条")

    update = {
        "news_list": news_list,
        "news_count": len(news_list),
        "data_source": "fetch",
        "current_step": f"获取到 {len(news_list)} 条新闻",
        "progress_percentage": WORKFLOW_CONFIG.PROGRESS_DATA_FETCH,
        "processing_steps": [f"📥 获取新闻数据：{len(news_list)} 条"]
    }

    logger.info(f"✅ 数据获取完成: news_count={len(news_list)}, elapsed={elapsed:.2f}ms")
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")

    return update
