"""
爬虫管理器
负责管理多个爬虫实例
支持普通爬虫和两阶段爬虫
"""

import os
import yaml
from typing import List, Dict, Union, Optional
from ..database import Database
from .base_crawler import GenericCrawler
from .two_stage_crawler import TwoStageCrawler
from ..post_processor import create_processor_from_config


class CrawlerManager:
    """爬虫管理器"""

    def __init__(self, config_path: Optional[str] = None, db_path: str = "data/news.db"):
        from news_crawler import DEFAULT_CONFIG_PATH
        
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH
        
        self.config_path = config_path
        self.database = Database(db_path)
        self.crawlers: List[Union[GenericCrawler, TwoStageCrawler]] = []
        self.load_config()

    def load_config(self):
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            print(f"配置文件不存在: {self.config_path}")
            return

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 提取通用配置
        common_config = config.get('common', {})

        # 检查是否启用两阶段爬取
        two_stage_enabled = common_config.get('two_stage_crawl', False)

        # 初始化各个爬虫
        sites_config = config.get('sites', [])
        for site_config in sites_config:
            if site_config.get('enabled', False):
                # 添加通用配置到每个站点配置
                site_config['common'] = common_config

                # 创建站点特定的后处理器
                global_post_processor = common_config.get('post_processor', {})
                site_post_processor = site_config.get('post_processor', {})
                post_processor = create_processor_from_config(global_post_processor, site_post_processor)
                
                # 为每个站点创建独立的数据库实例（带后处理器）
                site_database = Database(self.database.db_path, post_processor=post_processor)

                # 根据配置选择爬虫类型
                if two_stage_enabled or 'detail_config' in site_config:
                    # 使用两阶段爬虫
                    crawler = TwoStageCrawler(site_config, site_database)
                    self.crawlers.append(crawler)
                    print(f"已加载两阶段爬虫: {crawler.name}")
                else:
                    # 使用普通爬虫
                    crawler = GenericCrawler(site_config, site_database)
                    self.crawlers.append(crawler)
                    print(f"已加载爬虫: {crawler.name}")

        print(f"\n总共加载了 {len(self.crawlers)} 个爬虫")

    def run_all(self) -> Dict[str, int]:
        """运行所有爬虫"""
        results = {}

        for crawler in self.crawlers:
            print(f"\n{'#'*60}")
            print(f"# 运行爬虫: {crawler.name}")
            print(f"{'#'*60}")

            try:
                count = crawler.run()
                results[crawler.name] = count
                print(f"✓ {crawler.name} 完成，抓取了 {count} 条新闻")
            except Exception as e:
                print(f"✗ {crawler.name} 失败: {e}")
                results[crawler.name] = 0

        return results

    def run_crawler(self, site_name: str) -> int:
        """运行指定爬虫"""
        for crawler in self.crawlers:
            if crawler.name == site_name:
                return crawler.run()
        print(f"未找到爬虫: {site_name}")
        return 0

    def get_statistics(self):
        """获取统计信息"""
        return self.database.get_statistics()
    
    def get_statistics_with_urls(self):
        """获取统计信息（包含URL去重统计）"""
        return self.database.get_statistics_with_urls()

    def get_latest_news(self, limit: int = 30):
        """获取最新新闻"""
        return self.database.get_latest_news(limit)

    def get_hot_news(self, limit: int = 15):
        """获取实时热榜"""
        return self.database.get_news_by_category('hot_news', limit)

    def get_today_focus(self, limit: int = 15):
        """获取今日关注"""
        return self.database.get_news_by_category('today_focus', limit)

    def search_news(self, keyword: str, limit: int = 50):
        """搜索新闻"""
        return self.database.search_news(keyword, limit)

    def clear_old_news(self, days: int = 7):
        """清理旧新闻"""
        return self.database.clear_old_news(days)
    
    def clear_all_news(self) -> int:
        """清除所有新闻数据"""
        return self.database.clear_all_news()
