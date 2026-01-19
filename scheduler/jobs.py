"""
定时任务具体实现
包含爬取、同步、清理等任务
"""
import os
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


# ==================== 爬取任务 ====================

def crawl_news_job(config: Optional[Dict] = None):
    """
    爬取新闻任务
    
    使用集成的爬虫服务直接调用
    
    Args:
        config: 爬虫配置（可选）
            - site_name: 指定站点名称（只爬取该站点）
            - force_reload: 是否强制重新抓取（清理 crawled_urls，默认 False）
    """
    config = config or {}
    job_start = datetime.now()
    
    logger.info("=" * 60)
    logger.info(f"[定时任务] 开始爬取新闻 - {job_start.isoformat()}")
    logger.info("=" * 60)
    
    try:
        # 使用集成的爬虫服务
        from core.crawler_service import get_crawler_service
        
        crawler_service = get_crawler_service()
        
        # 如果配置了强制重新抓取，先清理 crawled_urls
        force_reload = config.get("force_reload", False)
        if force_reload:
            logger.info("[定时任务] 强制重新抓取模式：清理已抓取的 URL 记录...")
            cleared_count = crawler_service.clear_crawled_urls()
            logger.info(f"[定时任务] 已清理 {cleared_count} 条 URL 记录，将重新抓取所有新闻")
        
        # 如果配置中指定了站点，只爬取该站点
        site_name = config.get("site_name")
        if site_name:
            count = crawler_service.crawl_site(site_name)
            results = {site_name: count}
        else:
            # 运行所有爬虫
            results = crawler_service.crawl_all()
        
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        total_count = sum(results.values())
        
        logger.info(f"[定时任务] 爬取完成")
        logger.info(f"  - 耗时: {duration:.2f}s")
        logger.info(f"  - 总计: {total_count} 条新闻")
        logger.info(f"  - 详情: {results}")
        
        return {
            "success": True,
            "total": total_count,
            "results": results,
            "duration": duration,
            "force_reload": force_reload
        }
        
    except Exception as e:
        logger.error(f"[定时任务] 爬取失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def crawl_and_refresh_job(config: Optional[Dict] = None):
    """
    爬取新闻并刷新数据库任务
    
    每天定时执行，爬取最新新闻并清理旧数据
    
    Args:
        config: 任务配置
            - days_to_keep: 保留天数（默认7天）
            - clear_before_crawl: 是否在爬取前清理（默认False）
    """
    config = config or {}
    job_start = datetime.now()
    
    logger.info("=" * 60)
    logger.info(f"[定时任务] 开始爬取并刷新数据库 - {job_start.isoformat()}")
    logger.info("=" * 60)
    
    try:
        from core.crawler_service import get_crawler_service
        
        crawler_service = get_crawler_service()
        days_to_keep = config.get("days_to_keep", 7)
        clear_before_crawl = config.get("clear_before_crawl", False)
        
        # 步骤1: 可选清理旧数据（在爬取前）
        if clear_before_crawl:
            logger.info(f"[定时任务] 清理 {days_to_keep} 天前的旧数据...")
            deleted_count = crawler_service.clear_old_news(days_to_keep)
            logger.info(f"[定时任务] 清理完成，删除了 {deleted_count} 条旧新闻")
        
        # 步骤2: 爬取新新闻
        logger.info("[定时任务] 开始爬取新新闻...")
        results = crawler_service.crawl_all()
        total_count = sum(results.values())
        
        # 步骤3: 清理旧数据（在爬取后，确保新数据已保存）
        if not clear_before_crawl:
            logger.info(f"[定时任务] 清理 {days_to_keep} 天前的旧数据...")
            deleted_count = crawler_service.clear_old_news(days_to_keep)
            logger.info(f"[定时任务] 清理完成，删除了 {deleted_count} 条旧新闻")
        
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        
        # 获取统计信息
        stats = crawler_service.get_statistics()
        
        logger.info(f"[定时任务] 爬取并刷新完成")
        logger.info(f"  - 耗时: {duration:.2f}s")
        logger.info(f"  - 新增: {total_count} 条新闻")
        logger.info(f"  - 数据库总数: {stats.get('total', 0)} 条")
        logger.info(f"  - 详情: {results}")
        
        return {
            "success": True,
            "new_count": total_count,
            "total_count": stats.get('total', 0),
            "results": results,
            "duration": duration
        }
        
    except Exception as e:
        logger.error(f"[定时任务] 爬取并刷新失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ==================== 同步任务 ====================

def sync_news_job():
    """
    同步新闻数据任务
    
    从爬虫数据库同步数据到本地数据库
    用于数据备份或分布式部署场景
    """
    job_start = datetime.now()
    
    logger.info("=" * 60)
    logger.info(f"[定时任务] 开始同步新闻 - {job_start.isoformat()}")
    logger.info("=" * 60)
    
    try:
        from core.crawler_service import get_crawler_service
        
        # 获取爬虫服务（已统一使用 Database 类）
        crawler = get_crawler_service()
        
        # 获取今天的新闻（数据已在 Database 中，无需同步）
        today_news = crawler.get_today_news()
        
        if not today_news:
            logger.info("没有新的新闻")
            return {"success": True, "synced": 0}
        
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        
        logger.info(f"[定时任务] 检查完成")
        logger.info(f"  - 耗时: {duration:.2f}s")
        logger.info(f"  - 今日新闻数: {len(today_news)} 条")
        
        return {
            "success": True,
            "synced": len(today_news),
            "skipped": 0,
            "duration": duration
        }
        
    except Exception as e:
        logger.error(f"[定时任务] 同步失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ==================== 清理任务 ====================

def cleanup_old_news_job(days_to_keep: int = 30):
    """
    清理旧新闻数据任务
    
    Args:
        days_to_keep: 保留天数
    """
    job_start = datetime.now()
    
    logger.info("=" * 60)
    logger.info(f"[定时任务] 开始清理旧数据 - {job_start.isoformat()}")
    logger.info(f"  - 保留天数: {days_to_keep}")
    logger.info("=" * 60)
    
    try:
        from core.crawler_service import get_crawler_service
        
        crawler_service = get_crawler_service()
        
        # 清理旧新闻
        deleted_count = crawler_service.clear_old_news(days_to_keep)
        
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        
        logger.info(f"[定时任务] 清理完成")
        logger.info(f"  - 删除新闻: {deleted_count} 条")
        logger.info(f"  - 耗时: {duration:.2f}s")
        
        return {
            "success": True,
            "deleted": deleted_count,
            "days_to_keep": days_to_keep,
            "duration": duration
        }
        
    except Exception as e:
        logger.error(f"[定时任务] 清理失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ==================== 清除所有数据任务 ====================

def clear_all_news_job():
    """
    清除所有新闻数据任务
    
    每周执行一次，清除数据库中的所有新闻数据
    """
    job_start = datetime.now()
    
    logger.info("=" * 60)
    logger.info(f"[定时任务] 开始清除所有新闻数据 - {job_start.isoformat()}")
    logger.info("=" * 60)
    
    try:
        from core.crawler_service import get_crawler_service
        
        crawler_service = get_crawler_service()
        
        # 获取清除前的统计信息
        stats_before = crawler_service.get_statistics()
        total_before = stats_before.get("total", 0)
        
        # 清除所有新闻
        deleted_count = crawler_service.clear_all_news()
        
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()
        
        logger.info(f"[定时任务] 清除完成")
        logger.info(f"  - 删除新闻: {deleted_count} 条")
        logger.info(f"  - 耗时: {duration:.2f}s")
        
        return {
            "success": True,
            "deleted": deleted_count,
            "total_before": total_before,
            "duration": duration
        }
        
    except Exception as e:
        logger.error(f"[定时任务] 清除所有新闻失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ==================== 健康检查任务 ====================

def health_check_job():
    """
    系统健康检查任务
    
    检查数据库连接、外部服务等
    """
    logger.info("[定时任务] 执行健康检查")
    
    checks = {
        "database": False,
        "crawler_service": False,
        "timestamp": datetime.now().isoformat()
    }
    
    # 检查爬虫服务
    try:
        from core.crawler_service import get_crawler_service
        crawler = get_crawler_service()
        stats = crawler.get_statistics()
        checks["crawler_service"] = True
        checks["news_count"] = stats.get("total", 0)
    except Exception as e:
        logger.warning(f"爬虫服务检查失败: {e}")
    
    # 检查数据库
    try:
        from core.crawler_service import get_crawler_service
        crawler = get_crawler_service()
        crawler.get_stats()
        checks["database"] = True
    except Exception as e:
        logger.warning(f"数据库检查失败: {e}")
    
    all_healthy = all([checks["database"], checks["crawler_service"]])
    checks["healthy"] = all_healthy
    
    logger.info(f"[定时任务] 健康检查完成: {'✅ 健康' if all_healthy else '⚠️ 异常'}")
    
    return checks
