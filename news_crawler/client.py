"""
新闻爬虫模块客户端接口
提供统一的爬虫接口供其他系统调用
封装 CrawlerManager，提供更高级的 API
"""

from typing import List, Dict, Optional, Callable
from pathlib import Path
from models.news import NewsItem
from .database import Database
from .crawlers.manager import CrawlerManager
from .logger_config import get_crawler_logger

logger = get_crawler_logger(__name__)


class NewsCrawlerAPI:
    """
    新闻爬虫API类
    提供统一的接口供外部系统调用
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        db_path: str = "data/news.db",
        verbose: bool = True
    ):
        """
        初始化新闻爬虫API
        
        Args:
            config_path: 配置文件路径，默认为项目根目录下的 config/sites.yaml
            db_path: 数据库文件路径，默认为 data/news.db
            verbose: 是否显示详细日志，默认为 True
        """
        from news_crawler import DEFAULT_CONFIG_PATH
        
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH
        
        self.config_path = config_path
        self.db_path = db_path
        self.verbose = verbose
        self.manager = CrawlerManager(config_path=config_path, db_path=db_path)
    
    def crawl_all(self, callback: Optional[Callable[[str, int], None]] = None) -> Dict[str, int]:
        """
        运行所有启用的爬虫
        
        Args:
            callback: 可选的回调函数，格式为 callback(site_name, count)
                     在每个爬虫完成后调用，传入站点名称和抓取数量
        
        Returns:
            字典，键为站点名称，值为抓取的新闻数量
            示例: {"TopHub网易热榜": 15, "网易新闻今日推荐": 10}
        """
        if self.verbose:
            logger.info("开始运行所有爬虫...")
        
        results = self.manager.run_all()
        
        if callback:
            for site_name, count in results.items():
                callback(site_name, count)
        
        if self.verbose:
            total = sum(results.values())
            logger.info(f"爬取完成，共抓取 {total} 条新闻")
        
        return results
    
    def crawl_site(self, site_name: str) -> int:
        """
        运行指定站点的爬虫
        
        Args:
            site_name: 站点名称（配置中的 name 字段）
        
        Returns:
            抓取的新闻数量
        """
        if self.verbose:
            logger.info(f"开始运行爬虫: {site_name}")
        
        count = self.manager.run_crawler(site_name)
        
        if self.verbose:
            logger.info(f"完成，抓取了 {count} 条新闻")
        
        return count
    
    def get_latest_news(self, limit: int = 30) -> List[NewsItem]:
        """
        获取最新新闻
        
        Args:
            limit: 返回数量，默认30条
        
        Returns:
            新闻列表
        """
        return self.manager.get_latest_news(limit)
    
    def get_hot_news(self, limit: int = 15) -> List[NewsItem]:
        """
        获取实时热榜新闻
        
        Args:
            limit: 返回数量，默认15条
        
        Returns:
            新闻列表
        """
        return self.manager.get_hot_news(limit)
    
    def get_today_focus(self, limit: int = 15) -> List[NewsItem]:
        """
        获取今日关注新闻
        
        Args:
            limit: 返回数量，默认15条
        
        Returns:
            新闻列表
        """
        return self.manager.get_today_focus(limit)
    
    def search_news(self, keyword: str, limit: int = 50) -> List[NewsItem]:
        """
        搜索新闻
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量，默认50条
        
        Returns:
            新闻列表
        """
        return self.manager.search_news(keyword, limit)
    
    def get_statistics(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典，包含：
            - total: 总新闻数
            - by_category: 按分类统计
            - by_source: 按来源站点统计
            - latest_update: 最新更新时间
            - crawled_urls_count: 已抓取URL数（如果调用get_statistics_with_urls）
        """
        return self.manager.get_statistics()
    
    def get_statistics_with_urls(self) -> Dict:
        """
        获取统计信息（包含URL去重统计）
        
        Returns:
            统计信息字典，包含URL去重相关统计
        """
        return self.manager.get_statistics_with_urls()
    
    def clear_old_news(self, days: int = 7) -> int:
        """
        清理旧新闻
        
        Args:
            days: 清理多少天前的新闻，默认7天
        
        Returns:
            清理的新闻数量
        """
        return self.manager.clear_old_news(days)
    
    def clear_all_news(self) -> int:
        """
        清除所有新闻数据
        
        Returns:
            删除的新闻数量
        """
        return self.manager.clear_all_news()
    
    def get_database(self) -> Database:
        """
        获取数据库实例（用于高级操作）
        
        Returns:
            Database实例
        """
        return self.manager.database
    
    def get_news_by_url(self, url: str) -> Optional[NewsItem]:
        """
        根据URL获取新闻（如果存在）
        
        Args:
            url: 新闻URL
        
        Returns:
            NewsItem对象，如果不存在则返回None
        """
        conn = self.manager.database.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM news WHERE url = ?", (url,))
            row = cursor.fetchone()
            if row:
                return self.manager.database._row_to_news(row)
            return None
        except Exception as e:
            # 记录错误但不抛出，返回None表示未找到
            if self.verbose:
                logger.debug(f"查询新闻失败 [{url}]: {e}")
            return None
        # 注意：不关闭连接，因为这是共享的连接池连接
    
    def is_url_crawled(self, url: str) -> bool:
        """
        检查URL是否已被抓取
        
        Args:
            url: 新闻URL
        
        Returns:
            True表示已抓取，False表示未抓取
        """
        return self.manager.database.is_url_crawled(url)

