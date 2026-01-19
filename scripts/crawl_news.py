#!/usr/bin/env python3
"""
手动启动爬虫抓取新闻数据脚本
支持运行所有爬虫或指定站点，支持强制重新抓取
"""
import sys
import argparse
import logging
from datetime import datetime

# 添加项目根目录到路径
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def crawl_all(force_reload: bool = False, verbose: bool = False, clear_db: bool = False):
    """
    运行所有爬虫
    
    Args:
        force_reload: 是否强制重新抓取（清理 crawled_urls）
        verbose: 是否显示详细日志
        clear_db: 是否清空数据库（删除所有新闻数据）
        
    Returns:
        爬取结果字典
    """
    try:
        from core.crawler_service import get_crawler_service
        
        logger.info("=" * 80)
        logger.info("开始运行所有爬虫")
        if clear_db:
            logger.info("⚠️  清空数据库模式（将删除所有新闻数据）")
        if force_reload:
            logger.info("⚠️  强制重新抓取模式（将清理所有已抓取的 URL 记录）")
        logger.info("=" * 80)
        
        crawler = get_crawler_service()
        
        # 如果启用清空数据库，先清空所有新闻数据
        if clear_db:
            logger.info("\n正在清空数据库...")
            try:
                stats_before = crawler.get_stats()
                total_before = stats_before.get('total_news', 0)
                deleted_count = crawler.clear_all_news()
                logger.info(f"✅ 已清空数据库，删除了 {deleted_count} 条新闻\n")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ 清空数据库失败: {error_msg}")
                if "disk I/O error" in error_msg.lower() or "database is locked" in error_msg.lower():
                    logger.error("\n" + "=" * 80)
                    logger.error("数据库访问错误！可能的解决方案：")
                    logger.error("=" * 80)
                    logger.error("1. 检查是否有其他进程正在使用数据库")
                    logger.error("   - 关闭其他可能访问数据库的程序")
                    logger.error("   - 检查是否有定时任务正在运行")
                    logger.error("\n2. 如果WAL文件损坏，尝试删除WAL相关文件：")
                    logger.error("   - 删除 data/news.db-wal")
                    logger.error("   - 删除 data/news.db-shm")
                    logger.error("\n3. 检查磁盘空间和文件权限")
                    logger.error("=" * 80)
                return {
                    "success": False,
                    "error": f"清空数据库失败: {error_msg}"
                }
        else:
            # 显示爬取前的统计信息
            try:
                stats_before = crawler.get_stats()
                logger.info(f"\n爬取前数据库统计:")
                logger.info(f"   - 总新闻数: {stats_before.get('total_news', 0)}")
                logger.info(f"   - 今日新闻: {stats_before.get('today_count', 0)}")
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"获取爬取前统计信息失败: {error_msg}")
                if "disk I/O error" in error_msg.lower():
                    logger.warning("  提示: 数据库可能被锁定或损坏，请检查数据库文件状态")
        
        # 如果启用强制重新抓取，先清理 crawled_urls
        if force_reload:
            logger.info("\n正在清理已抓取的 URL 记录...")
            cleared_count = crawler.clear_crawled_urls()
            logger.info(f"✅ 已清理 {cleared_count} 条 URL 记录，将重新抓取所有新闻\n")
        
        logger.info("开始运行爬虫...")
        logger.info("（这可能需要几分钟时间，请耐心等待）\n")
        
        start_time = datetime.now()
        results = crawler.crawl_all()
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        total = sum(results.values())
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 爬取完成！")
        logger.info(f"   - 总耗时: {duration:.2f} 秒")
        logger.info(f"   - 总计抓取: {total} 条新闻")
        logger.info(f"\n各站点抓取结果:")
        for site, count in results.items():
            logger.info(f"   - {site}: {count} 条")
        logger.info("=" * 80)
        
        # 显示爬取后的统计信息
        try:
            stats_after = crawler.get_stats()
            logger.info(f"\n爬取后数据库统计:")
            
            # 显示总新闻数及变化量
            total_after = stats_after.get('total_news', 0)
            if 'stats_before' in locals():
                total_before = stats_before.get('total_news', 0)
                change = total_after - total_before
                if change > 0:
                    logger.info(f"   - 总新闻数: {total_after} (新增 {change} 条)")
                elif change < 0:
                    logger.info(f"   - 总新闻数: {total_after} (减少 {abs(change)} 条)")
                else:
                    logger.info(f"   - 总新闻数: {total_after} (无变化)")
            else:
                logger.info(f"   - 总新闻数: {total_after}")
            
            logger.info(f"   - 今日新闻: {stats_after.get('today_count', 0)}")
            logger.info(f"   - 分类数: {stats_after.get('total_categories', 0)}")
            logger.info(f"   - 来源数: {stats_after.get('total_sources', 0)}")
            logger.info(f"   - 日期数: {stats_after.get('total_dates', 0)}")
            
            # 显示分类分布（前5个）
            by_category = stats_after.get('by_category', [])
            if by_category:
                logger.info(f"\n分类分布（前5个）:")
                for cat_info in by_category[:5]:
                    category = cat_info.get('category', '未知')
                    count = cat_info.get('count', 0)
                    logger.info(f"   - {category}: {count} 条")
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"获取统计信息失败: {error_msg}")
            if "disk I/O error" in error_msg.lower():
                logger.warning("  提示: 数据库可能被锁定或损坏，请检查数据库文件状态")
        
        return {
            "success": True,
            "total": total,
            "results": results,
            "duration": duration
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 爬取失败: {error_msg}")
        
        # 如果是数据库I/O错误，提供解决建议
        if "disk I/O error" in error_msg.lower() or "database is locked" in error_msg.lower():
            logger.error("\n" + "=" * 80)
            logger.error("数据库访问错误！可能的解决方案：")
            logger.error("=" * 80)
            logger.error("1. 检查是否有其他进程正在使用数据库")
            logger.error("   - 关闭其他可能访问数据库的程序")
            logger.error("   - 检查是否有定时任务正在运行")
            logger.error("\n2. 如果WAL文件损坏，尝试删除WAL相关文件：")
            logger.error("   - 删除 data/news.db-wal")
            logger.error("   - 删除 data/news.db-shm")
            logger.error("\n3. 检查磁盘空间和文件权限")
            logger.error("=" * 80)
        
        return {
            "success": False,
            "error": error_msg
        }


def crawl_site(site_name: str, force_reload: bool = False, verbose: bool = False, clear_db: bool = False):
    """
    运行指定站点的爬虫
    
    Args:
        site_name: 站点名称
        force_reload: 是否强制重新抓取（清理该站点的 crawled_urls）
        verbose: 是否显示详细日志
        clear_db: 是否清空数据库（删除所有新闻数据）
        
    Returns:
        爬取结果字典
    """
    try:
        from core.crawler_service import get_crawler_service
        
        logger.info("=" * 80)
        logger.info(f"开始运行爬虫: {site_name}")
        if clear_db:
            logger.info("⚠️  清空数据库模式（将删除所有新闻数据）")
        if force_reload:
            logger.info("⚠️  强制重新抓取模式")
        logger.info("=" * 80)
        
        crawler = get_crawler_service()
        
        # 如果启用清空数据库，先清空所有新闻数据
        if clear_db:
            logger.info("\n正在清空数据库...")
            try:
                stats_before = crawler.get_stats()
                total_before = stats_before.get('total_news', 0)
                deleted_count = crawler.clear_all_news()
                logger.info(f"✅ 已清空数据库，删除了 {deleted_count} 条新闻\n")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ 清空数据库失败: {error_msg}")
                if "disk I/O error" in error_msg.lower() or "database is locked" in error_msg.lower():
                    logger.error("\n" + "=" * 80)
                    logger.error("数据库访问错误！可能的解决方案：")
                    logger.error("=" * 80)
                    logger.error("1. 检查是否有其他进程正在使用数据库")
                    logger.error("   - 关闭其他可能访问数据库的程序")
                    logger.error("   - 检查是否有定时任务正在运行")
                    logger.error("\n2. 如果WAL文件损坏，尝试删除WAL相关文件：")
                    logger.error("   - 删除 data/news.db-wal")
                    logger.error("   - 删除 data/news.db-shm")
                    logger.error("\n3. 检查磁盘空间和文件权限")
                    logger.error("=" * 80)
                return {
                    "success": False,
                    "error": f"清空数据库失败: {error_msg}"
                }
        else:
            # 显示爬取前的统计信息
            try:
                stats_before = crawler.get_stats()
                logger.info(f"\n爬取前数据库统计:")
                logger.info(f"   - 总新闻数: {stats_before.get('total_news', 0)}")
                logger.info(f"   - 今日新闻: {stats_before.get('today_count', 0)}")
            except Exception as e:
                logger.warning(f"获取爬取前统计信息失败: {e}")
        
        # 如果启用强制重新抓取，先清理 crawled_urls
        if force_reload:
            logger.info("\n正在清理已抓取的 URL 记录...")
            cleared_count = crawler.clear_crawled_urls()
            logger.info(f"✅ 已清理 {cleared_count} 条 URL 记录\n")
        
        logger.info(f"开始运行爬虫: {site_name}...\n")
        
        start_time = datetime.now()
        count = crawler.crawl_site(site_name)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 爬取完成！")
        logger.info(f"   - 耗时: {duration:.2f} 秒")
        logger.info(f"   - 抓取数量: {count} 条")
        logger.info("=" * 80)
        
        # 显示爬取后的统计信息
        try:
            stats_after = crawler.get_stats()
            logger.info(f"\n爬取后数据库统计:")
            
            # 显示总新闻数及变化量
            total_after = stats_after.get('total_news', 0)
            if 'stats_before' in locals():
                total_before = stats_before.get('total_news', 0)
                change = total_after - total_before
                if change > 0:
                    logger.info(f"   - 总新闻数: {total_after} (新增 {change} 条)")
                elif change < 0:
                    logger.info(f"   - 总新闻数: {total_after} (减少 {abs(change)} 条)")
                else:
                    logger.info(f"   - 总新闻数: {total_after} (无变化)")
            else:
                logger.info(f"   - 总新闻数: {total_after}")
            
            logger.info(f"   - 今日新闻: {stats_after.get('today_count', 0)}")
            logger.info(f"   - 分类数: {stats_after.get('total_categories', 0)}")
            logger.info(f"   - 来源数: {stats_after.get('total_sources', 0)}")
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"获取爬取后统计信息失败: {error_msg}")
            if "disk I/O error" in error_msg.lower():
                logger.warning("  提示: 数据库可能被锁定或损坏，请检查数据库文件状态")
        
        return {
            "success": True,
            "site": site_name,
            "count": count,
            "duration": duration
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 爬取失败: {error_msg}")
        
        # 如果是数据库I/O错误，提供解决建议
        if "disk I/O error" in error_msg.lower() or "database is locked" in error_msg.lower():
            logger.error("\n" + "=" * 80)
            logger.error("数据库访问错误！可能的解决方案：")
            logger.error("=" * 80)
            logger.error("1. 检查是否有其他进程正在使用数据库")
            logger.error("   - 关闭其他可能访问数据库的程序")
            logger.error("   - 检查是否有定时任务正在运行")
            logger.error("\n2. 如果WAL文件损坏，尝试删除WAL相关文件：")
            logger.error("   - 删除 data/news.db-wal")
            logger.error("   - 删除 data/news.db-shm")
            logger.error("\n3. 检查磁盘空间和文件权限")
            logger.error("=" * 80)
        
        return {
            "success": False,
            "error": error_msg
        }


def list_sites():
    """列出所有可用的站点"""
    try:
        from core.crawler_service import get_crawler_service
        import yaml
        
        # 从配置文件获取配置路径
        crawler = get_crawler_service()
        config_path = Path(crawler.config_path)
        
        if not config_path.exists():
            logger.error(f"配置文件不存在: {config_path}")
            logger.info(f"请检查配置文件路径: {crawler.config_path}")
            return
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        sites = config.get('sites', [])
        
        if not sites:
            logger.warning("配置文件中没有找到站点配置")
            return
        
        logger.info("=" * 80)
        logger.info("可用的站点列表:")
        logger.info("=" * 80)
        
        enabled_sites = []
        disabled_sites = []
        
        for site in sites:
            name = site.get('name', 'N/A')
            enabled = site.get('enabled', True)
            if enabled:
                enabled_sites.append(name)
            else:
                disabled_sites.append(name)
        
        if enabled_sites:
            logger.info("\n✅ 已启用的站点:")
            for name in enabled_sites:
                logger.info(f"  - {name}")
        
        if disabled_sites:
            logger.info("\n❌ 已禁用的站点:")
            for name in disabled_sites:
                logger.info(f"  - {name}")
        
        logger.info("=" * 80)
        logger.info(f"\n提示: 使用 --site 参数指定站点名称来运行单个爬虫")
        
    except Exception as e:
        logger.error(f"获取站点列表失败: {e}", exc_info=True)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='手动启动爬虫抓取新闻数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行所有爬虫
  python scripts/crawl_news.py

  # 强制重新抓取所有新闻
  python scripts/crawl_news.py --force

  # 清空数据库后重新爬取
  python scripts/crawl_news.py --clear-db

  # 运行指定站点
  python scripts/crawl_news.py --site "TopHub网易热榜"

  # 列出所有可用站点
  python scripts/crawl_news.py --list-sites

  # 显示详细日志
  python scripts/crawl_news.py --verbose
        """
    )
    
    parser.add_argument(
        '--site', '-s',
        type=str,
        metavar='SITE_NAME',
        help='指定要运行的站点名称（如果不指定，则运行所有站点）'
    )
    
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='强制重新抓取（清理所有已抓取的 URL 记录）'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='显示详细日志'
    )
    
    parser.add_argument(
        '--list-sites', '-l',
        action='store_true',
        help='列出所有可用的站点'
    )
    
    parser.add_argument(
        '--clear-db',
        action='store_true',
        help='清空数据库（删除所有新闻数据，然后再爬取）'
    )
    
    args = parser.parse_args()
    
    # 如果指定了列出站点，只执行这个操作
    if args.list_sites:
        list_sites()
        return 0
    
    # 运行爬虫
    if args.site:
        # 运行指定站点
        result = crawl_site(args.site, force_reload=args.force, verbose=args.verbose, clear_db=args.clear_db)
    else:
        # 运行所有爬虫
        result = crawl_all(force_reload=args.force, verbose=args.verbose, clear_db=args.clear_db)
    
    # 根据结果返回退出码
    if result.get("success"):
        return 0
    else:
        logger.error(f"爬取失败: {result.get('error', '未知错误')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

