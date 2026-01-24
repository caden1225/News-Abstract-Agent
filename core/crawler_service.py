"""
新闻爬虫服务
提供统一的爬虫接口供主逻辑调用
整合所有数据访问，统一返回 Dict 模型
"""
import os
import logging
import json
from typing import List, Dict, Optional
from pathlib import Path
from datetime import date, datetime

from news_crawler import NewsCrawlerAPI, DEFAULT_CONFIG_PATH
from models.news import NewsItem

logger = logging.getLogger(__name__)


class CrawlerService:
    """
    新闻爬虫服务类
    
    封装 news_crawler 模块，提供统一的接口供主项目调用
    自动处理路径配置和错误处理
    """
    
    _instance: Optional['CrawlerService'] = None
    _crawler: Optional[NewsCrawlerAPI] = None
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        db_path: Optional[str] = None,
        verbose: bool = False
    ):
        """
        初始化爬虫服务
        
        Args:
            config_path: 配置文件路径，默认从主配置读取
            db_path: 数据库文件路径，默认从主配置读取
            verbose: 是否显示详细日志
        """
        # 从主配置读取爬虫配置
        try:
            from llm_utils.config import config
            
            crawler_config = config.get("crawler", {})
            
            if config_path is None:
                config_path = crawler_config.get("config_path", DEFAULT_CONFIG_PATH)
            
            if db_path is None:
                # 从配置文件读取数据库路径
                db_path = crawler_config.get("db_path", "data/news.db")
                # 如果是相对路径，转换为绝对路径
                if not os.path.isabs(db_path):
                    project_root = Path(__file__).parent.parent
                    db_path = str((project_root / db_path).resolve())
                # 确保 data 目录存在
                db_path_obj = Path(db_path)
                db_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            if verbose is False:
                verbose = crawler_config.get("verbose", False)
        except Exception as e:
            logger.warning(f"读取爬虫配置失败，使用默认值: {e}")
            if config_path is None:
                config_path = DEFAULT_CONFIG_PATH
            if db_path is None:
                # 默认路径
                project_root = Path(__file__).parent.parent
                db_path = str((project_root / "data" / "news.db").resolve())
                # 确保 data 目录存在
                db_path_obj = Path(db_path)
                db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        self.config_path = config_path
        self.db_path = db_path
        self.verbose = verbose
        
        logger.info(f"初始化爬虫服务: config={config_path}, db={db_path}")
        
        # 延迟初始化 crawler（避免启动时立即连接数据库）
        self._crawler = None
    
    @property
    def crawler(self) -> NewsCrawlerAPI:
        """获取爬虫 API 实例（懒加载）"""
        if self._crawler is None:
            self._crawler = NewsCrawlerAPI(
                config_path=self.config_path,
                db_path=self.db_path,
                verbose=self.verbose
            )
        return self._crawler
    
    def crawl_all(self) -> Dict[str, int]:
        """
        运行所有启用的爬虫
        
        Returns:
            字典，键为站点名称，值为抓取的新闻数量
        """
        try:
            logger.info("开始运行所有爬虫...")
            results = self.crawler.crawl_all()
            total = sum(results.values())
            logger.info(f"爬取完成，共抓取 {total} 条新闻: {results}")
            return results
        except Exception as e:
            logger.error(f"爬取失败: {e}", exc_info=True)
            return {}
    
    def crawl_site(self, site_name: str) -> int:
        """
        运行指定站点的爬虫
        
        Args:
            site_name: 站点名称
            
        Returns:
            抓取的新闻数量
        """
        try:
            logger.info(f"开始运行爬虫: {site_name}")
            count = self.crawler.crawl_site(site_name)
            logger.info(f"完成，抓取了 {count} 条新闻")
            return count
        except Exception as e:
            logger.error(f"爬取站点 {site_name} 失败: {e}", exc_info=True)
            return 0
    
    def get_latest_news(self, limit: int = 30) -> List[NewsItem]:
        """
        获取最新新闻
        
        Args:
            limit: 返回数量
            
        Returns:
            新闻列表
        """
        try:
            return self.crawler.get_latest_news(limit)
        except Exception as e:
            logger.error(f"获取最新新闻失败: {e}", exc_info=True)
            return []
    
    def get_hot_news(self, limit: int = 15) -> List[NewsItem]:
        """
        获取实时热榜新闻
        
        Args:
            limit: 返回数量
            
        Returns:
            新闻列表
        """
        try:
            return self.crawler.get_hot_news(limit)
        except Exception as e:
            logger.error(f"获取热榜新闻失败: {e}", exc_info=True)
            return []
    
    def get_today_focus(self, limit: int = 15) -> List[NewsItem]:
        """
        获取今日关注新闻
        
        Args:
            limit: 返回数量
            
        Returns:
            新闻列表
        """
        try:
            return self.crawler.get_today_focus(limit)
        except Exception as e:
            logger.error(f"获取今日关注失败: {e}", exc_info=True)
            return []
    
    def search_news(self, keyword: str, limit: int = 50) -> List[NewsItem]:
        """
        搜索新闻
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量
            
        Returns:
            新闻列表
        """
        try:
            return self.crawler.search_news(keyword, limit)
        except Exception as e:
            logger.error(f"搜索新闻失败: {e}", exc_info=True)
            return []
    
    def get_statistics(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        try:
            stats = self.crawler.get_statistics()
            # 统一格式
            return {
                'total_news': stats.get('total', 0),
                'by_category': stats.get('by_category', []),
                'today_count': stats.get('today_count', 0),
                'total_categories': stats.get('total_categories', 0),
                'total_dates': stats.get('total_dates', 0),
                'total_sources': stats.get('total_sources', 0),
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}", exc_info=True)
            return {}
    
    def clear_old_news(self, days: int = 7) -> int:
        """
        清理旧新闻
        
        Args:
            days: 清理多少天前的新闻
            
        Returns:
            清理的新闻数量
        """
        try:
            count = self.crawler.clear_old_news(days)
            logger.info(f"清理了 {count} 条 {days} 天前的旧新闻")
            return count
        except Exception as e:
            logger.error(f"清理旧新闻失败: {e}", exc_info=True)
            return 0
    
    def clear_all_news(self) -> int:
        """
        清除所有新闻数据
        
        Returns:
            删除的新闻数量
        """
        try:
            count = self.crawler.clear_all_news()
            logger.info(f"清除了所有新闻数据，共 {count} 条")
            return count
        except Exception as e:
            logger.error(f"清除所有新闻失败: {e}", exc_info=True)
            return 0
    
    def clear_crawled_urls(self, days: Optional[int] = None) -> int:
        """
        清理已抓取的 URL 记录
        
        用于强制重新抓取已抓取过的新闻
        
        Args:
            days: 如果指定，只清理多少天前的记录；如果为 None，清理所有记录
            
        Returns:
            清理的记录数量
        """
        try:
            db = self.get_database()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            if days is None:
                # 清理所有记录
                cursor.execute("DELETE FROM crawled_urls")
            else:
                # 清理指定天数前的记录
                cursor.execute("""
                    DELETE FROM crawled_urls
                    WHERE datetime(crawled_at) < datetime('now', '-' || ? || ' days')
                """, (days,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"清理了 {deleted_count} 条 crawled_urls 记录")
            # 优化：不关闭连接，让连接池复用
            return deleted_count
        except Exception as e:
            logger.error(f"清理 crawled_urls 失败: {e}", exc_info=True)
            return 0
    
    def reset_crawl_status(self) -> Dict[str, int]:
        """
        重置爬取状态（清理所有 crawled_urls 记录）
        
        用于强制重新抓取所有新闻
        
        Returns:
            包含清理数量的字典
        """
        try:
            count = self.clear_crawled_urls()
            logger.info(f"已重置爬取状态，清理了 {count} 条 URL 记录")
            return {
                "cleared_urls": count,
                "message": "爬取状态已重置，下次爬取将重新抓取所有新闻"
            }
        except Exception as e:
            logger.error(f"重置爬取状态失败: {e}", exc_info=True)
            return {"cleared_urls": 0, "error": str(e)}
    
    def get_database(self):
        """获取数据库实例（用于高级操作）"""
        return self.crawler.get_database()
    
    # ==================== 数据查询方法（统一返回 Dict）====================
    
    def get_news_by_date(
        self,
        target_date: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """
        获取指定日期的新闻
        
        Args:
            target_date: 目标日期（YYYY-MM-DD格式）
            category: 可选的分类过滤
            
        Returns:
            新闻字典列表（统一格式）
        """
        try:
            # 优化：使用连接池，不关闭连接（连接会被复用）
            db = self.get_database()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # 优化：使用范围查询替代DATE()函数，可以利用索引
            # DATE(publish_time) = ? 改为 publish_time >= ? AND publish_time < ?
            from datetime import datetime, timedelta
            try:
                target_datetime = datetime.strptime(target_date, "%Y-%m-%d")
                start_time = target_datetime.strftime("%Y-%m-%d 00:00:00")
                end_time = (target_datetime + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
            except ValueError:
                # 如果日期格式不正确，回退到原方法
                start_time = target_date
                end_time = target_date
            
            sql = "SELECT * FROM news WHERE publish_time >= ? AND publish_time < ?"
            params = [start_time, end_time]
            
            if category:
                sql += " AND category = ?"
                params.append(category)
            
            sql += " ORDER BY publish_time DESC"
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            # 优化：不关闭连接，让连接池复用
            
            # 转换为统一格式
            result = [self._row_to_dict(row) for row in rows]
            
            logger.info(f"查询指定日期新闻: date={target_date}, category={category}, count={len(result)}")
            return result
        except Exception as e:
            logger.error(f"获取新闻失败: {e}", exc_info=True)
            return []
    
    def get_today_news(
        self,
        category: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        获取今天的新闻
        
        Args:
            category: 可选的分类过滤
            limit: 最多返回数量
            
        Returns:
            新闻字典列表
        """
        today = date.today().isoformat()
        result = self.get_news_by_date(today, category)
        if limit:
            result = result[:limit]
        return result
    
    def get_all_news(
        self,
        category: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        获取所有新闻（不限日期）
        
        Args:
            category: 可选的分类过滤
            limit: 最多返回数量
            
        Returns:
            新闻字典列表
        """
        try:
            db = self.get_database()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            sql = "SELECT * FROM news WHERE 1=1"
            params = []
            
            if category:
                sql += " AND category = ?"
                params.append(category)
            
            sql += " ORDER BY publish_time DESC"
            
            if limit:
                sql += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            # 优化：不关闭连接，让连接池复用
            
            result = [self._row_to_dict(row) for row in rows]
            
            logger.info(f"查询所有新闻: category={category}, count={len(result)}")
            return result
        except Exception as e:
            logger.error(f"获取所有新闻失败: {e}", exc_info=True)
            return []
    
    def get_news_by_keywords(
        self,
        keywords: List[str],
        limit: int = 10
    ) -> List[Dict]:
        """
        根据关键词搜索新闻
        
        Args:
            keywords: 关键词列表
            limit: 返回数量限制
            
        Returns:
            匹配的新闻列表（统一格式）
        """
        try:
            # 使用 NewsCrawlerAPI 的搜索功能
            if keywords:
                # 将多个关键词合并搜索
                keyword_str = " ".join(keywords)
                news_items = self.crawler.search_news(keyword_str, limit=limit)
                return [self._news_item_to_dict(item) for item in news_items]
            return []
        except Exception as e:
            logger.error(f"关键词搜索失败: {e}", exc_info=True)
            return []
    
    def get_stats(self) -> Dict:
        """
        获取数据库统计信息（统一格式）
        
        Returns:
            统计信息字典
        """
        try:
            db = self.get_database()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # 获取基本统计
            cursor.execute("""
                SELECT
                    COUNT(*) as total_news,
                    COUNT(DISTINCT category) as total_categories,
                    COUNT(DISTINCT DATE(publish_time)) as total_dates,
                    COUNT(DISTINCT source) as total_sources
                FROM news
            """)
            
            stats = dict(cursor.fetchone())
            
            # 获取今天的新闻数量
            today = date.today().isoformat()
            cursor.execute(
                "SELECT COUNT(*) as today_count FROM news WHERE DATE(publish_time) = ?",
                (today,)
            )
            stats['today_count'] = cursor.fetchone()['today_count']
            
            # 获取分类分布
            cursor.execute("""
                SELECT category, COUNT(*) as count
                FROM news
                GROUP BY category
                ORDER BY count DESC
            """)
            stats['by_category'] = [
                {"category": row['category'], "count": row['count']}
                for row in cursor.fetchall()
            ]
            
            # 优化：不关闭连接，让连接池复用
            return stats
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}", exc_info=True)
            return {}
    
    def get_available_dates(self, limit: int = 10) -> List[str]:
        """
        获取可用的新闻日期列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            日期列表（YYYY-MM-DD格式）
        """
        try:
            db = self.get_database()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT DATE(publish_time) as date
                FROM news
                ORDER BY date DESC
                LIMIT ?
            """, (limit,))
            
            dates = [row['date'] for row in cursor.fetchall()]
            # 优化：不关闭连接，让连接池复用
            return dates
        except Exception as e:
            logger.error(f"获取可用日期失败: {e}", exc_info=True)
            return []
    
    # ==================== 辅助方法 ====================
    
    def _news_item_to_dict(self, news_item: NewsItem) -> Dict:
        """
        将 NewsItem 转换为 Dict（统一数据模型）
        
        Args:
            news_item: NewsItem 对象
            
        Returns:
            统一格式的字典
        """
        # 提取日期
        published_date = self._extract_date(
            news_item.publish_time.isoformat() if news_item.publish_time else None
        )
        
        # 解析图片URLs
        images = []
        if news_item.image_urls:
            if isinstance(news_item.image_urls, str):
                try:
                    images = json.loads(news_item.image_urls)
                except (json.JSONDecodeError, TypeError):
                    images = []
            elif isinstance(news_item.image_urls, list):
                images = news_item.image_urls
        
        # 生成摘要
        content = news_item.content or ''
        summary = news_item.summary or (content[:100] + '...' if len(content) > 100 else content)
        
        return {
            'title': news_item.title or '',
            'link': news_item.url or '',  # 统一字段名
            'content': content,
            'summary': summary,
            'published_date': published_date,
            'category': news_item.category or '',
            'source': news_item.source or '',
            'images': images,
            'tags': news_item.tags if hasattr(news_item, 'tags') and news_item.tags else [],
            'ai_summary': '',  # 默认空
        }
    
    def _row_to_dict(self, row) -> Dict:
        """
        将数据库行转换为字典（统一格式）
        
        Args:
            row: 数据库行（sqlite3.Row 或 dict）
            
        Returns:
            统一格式的字典
        """
        if hasattr(row, 'keys'):
            d = dict(row)
        else:
            d = row
        
        # 字段映射
        if 'url' in d and 'link' not in d:
            d['link'] = d.pop('url')
        
        # 解析图片
        if 'image_urls' in d:
            image_urls_str = d.pop('image_urls')
            d['images'] = self._parse_image_urls(image_urls_str)
        else:
            d['images'] = []
        
        # 解析标签
        if 'tags' in d:
            tags_str = d.get('tags')
            if isinstance(tags_str, str):
                d['tags'] = self._parse_tags(tags_str)
            elif tags_str is None:
                d['tags'] = []
            # 如果已经是列表，保持不变
        else:
            d['tags'] = []
        
        # 提取日期
        if 'publish_time' in d:
            publish_time = d.pop('publish_time')
            d['published_date'] = self._extract_date(publish_time)
        else:
            d['published_date'] = date.today().isoformat()
        
        # 兼容字段
        if 'summary' not in d:
            content = d.get('content') or ''  # 处理 None 值
            d['summary'] = content[:100] + '...' if len(content) > 100 else content
        
        if 'ai_summary' not in d:
            d['ai_summary'] = ''
        
        return d
    
    def _parse_image_urls(self, image_urls_str: Optional[str]) -> List[str]:
        """
        解析 image_urls JSON 字符串
        
        Args:
            image_urls_str: JSON数组字符串
            
        Returns:
            图片URL列表
        """
        if not image_urls_str or image_urls_str == "None":
            return []
        
        try:
            urls = json.loads(image_urls_str)
            if isinstance(urls, list):
                return urls
            return []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def _parse_tags(self, tags_str: Optional[str]) -> List[str]:
        """
        解析 tags JSON 字符串
        
        Args:
            tags_str: JSON数组字符串
            
        Returns:
            标签列表
        """
        if not tags_str or tags_str == "None":
            return []
        
        try:
            tags = json.loads(tags_str)
            if isinstance(tags, list):
                return tags
            return []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def _extract_date(self, publish_time: Optional[str]) -> str:
        """
        从 publish_time 提取日期部分
        
        Args:
            publish_time: 时间戳字符串
            
        Returns:
            日期字符串（YYYY-MM-DD格式）
        """
        if not publish_time:
            return date.today().isoformat()
        
        # 尝试解析多种时间格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d"
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(str(publish_time), fmt)
                return dt.date().isoformat()
            except ValueError:
                continue
        
        return date.today().isoformat()
    
    @classmethod
    def get_instance(cls) -> 'CrawlerService':
        """
        获取单例实例（推荐使用）
        
        Returns:
            CrawlerService 实例
        """
        if cls._instance is None:
            cls._instance = cls(verbose=False)
        return cls._instance


# ==================== 便捷函数 ====================

def get_crawler_service() -> CrawlerService:
    """
    获取爬虫服务实例（单例）
    
    Returns:
        CrawlerService 实例
    """
    return CrawlerService.get_instance()

