"""
爬虫基类和核心逻辑
支持可配置的字段映射
"""

import time
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from models.news import NewsItem
from ..database import Database
from ..logger_config import get_crawler_logger

logger = get_crawler_logger(__name__)


class BaseCrawler(ABC):
    """爬虫基类"""

    def __init__(self, config: Dict, database: Database):
        self.config = config
        self.database = database
        self.name = config.get('name', 'Unknown')
        self.base_url = config.get('base_url', '')
        self.encoding = config.get('encoding', 'utf-8')
        self.request_delay = config.get('request_delay', 1)
        self.session = self._init_session()

    def _init_session(self) -> requests.Session:
        """初始化请求会话"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': self.config.get('common', {}).get(
                'user_agent',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
        })
        return session

    def _make_request(self, url: str, timeout: int = 30) -> Optional[requests.Response]:
        """发起HTTP请求"""
        max_retries = self.config.get('common', {}).get('retry_times', 3)
        retry_delay = self.config.get('common', {}).get('retry_delay', 5)

        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True
                )
                response.encoding = self.encoding
                return response
            except Exception as e:
                logger.debug(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {url}, 错误: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.warning(f"请求最终失败: {url}")
                    return None

    def _parse_datetime(self, date_str: str, format_str: str = None) -> Optional[datetime]:
        """解析日期时间字符串"""
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        # 常见格式尝试
        common_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d %H:%M',
            '%Y/%m/%d',
            '%m-%d %H:%M',
            '%H:%M',
            '%Y年%m月%d日',
        ]

        if format_str:
            try:
                return datetime.strptime(date_str, format_str)
            except ValueError:
                pass

        for fmt in common_formats:
            try:
                parsed_dt = datetime.strptime(date_str, fmt)
                # 如果只有时间没有日期，使用当前日期
                if parsed_dt.year == 1900:
                    now = datetime.now()
                    return datetime(now.year, now.month, now.day,
                                   parsed_dt.hour, parsed_dt.minute, parsed_dt.second)
                return parsed_dt
            except ValueError:
                continue

        return None

    def _extract_field(self, element, field_config: Dict) -> Any:
        """根据配置提取字段"""
        selector = field_config.get('selector', '')
        attr = field_config.get('attr', 'text')

        if not selector:
            return None

        try:
            if attr == 'text':
                result = element.select_one(selector)
                return result.get_text(strip=True) if result else None
            else:
                result = element.select_one(selector)
                if result:
                    value = result.get(attr, '')
                    # 处理相对URL
                    if attr in ['href', 'src'] and value:
                        value = urljoin(self.base_url, value)
                    return value
                return None
        except Exception as e:
            logger.debug(f"提取字段失败 [{selector}]: {e}")
            return None

    def _parse_news_item(self, item_element, field_mapping: Dict, category: str) -> Optional[NewsItem]:
        """解析单条新闻"""
        try:
            title_config = field_mapping.get('title', {})
            url_config = field_mapping.get('url', {})
            time_config = field_mapping.get('publish_time', {})
            image_config = field_mapping.get('image_url', {})
            source_config = field_mapping.get('source', {})
            desc_config = field_mapping.get('description', {})

            title = self._extract_field(item_element, title_config)
            news_url = self._extract_field(item_element, url_config)

            # 标题和URL是必需的
            if not title or not news_url:
                return None

            # 解析时间
            time_str = self._extract_field(item_element, time_config)
            time_format = time_config.get('format')
            publish_time = None
            if time_str:
                publish_time = self._parse_datetime(time_str, time_format)

            # 提取图片
            image_url = self._extract_field(item_element, image_config)
            image_urls = [image_url] if image_url else None

            # 提取来源
            source = self._extract_field(item_element, source_config) or self.name

            # 提取描述
            description = self._extract_field(item_element, desc_config)

            return NewsItem(
                title=title,
                url=news_url,
                source=source,
                source_site=self.name,
                category=category,
                publish_time=publish_time,
                image_urls=image_urls,
                description=description
            )
        except Exception as e:
            logger.debug(f"解析新闻项失败: {e}")
            return None

    def _fetch_category(self, category_config: Dict, category_name: str) -> List[NewsItem]:
        """抓取某个分类的新闻"""
        if not category_config.get('enabled', False):
            return []

        url = category_config.get('url', '')
        max_items = category_config.get('max_items', 15)
        field_mapping = category_config.get('field_mapping', {})

        if not url:
            logger.warning(f"未配置URL: {category_name}")
            return []

        logger.info(f"正在抓取 [{self.name}] - {category_name}")
        logger.debug(f"抓取URL: {url}")

        response = self._make_request(url)
        if not response:
            logger.warning(f"请求失败: {url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        container_selector = field_mapping.get('container', '')

        if not container_selector:
            logger.warning("未配置容器选择器")
            return []

        items = soup.select(container_selector)
        news_list = []

        for item_element in items[:max_items]:
            news_item = self._parse_news_item(item_element, field_mapping, category_name)
            if news_item:
                news_list.append(news_item)
                logger.debug(f"  ✓ {news_item.title[:50]}...")

        # 添加延迟
        if self.request_delay > 0:
            time.sleep(self.request_delay + random.uniform(0, 1))

        return news_list

    def crawl(self) -> Dict[str, List[NewsItem]]:
        """执行爬取任务"""
        logger.info(f"开始爬取: {self.name}")

        results = {}

        # 抓取实时热榜
        if 'hot_news' in self.config:
            hot_news = self._fetch_category(self.config['hot_news'], 'hot_news')
            results['hot_news'] = hot_news

        # 抓取今日关注
        if 'today_focus' in self.config:
            today_focus = self._fetch_category(self.config['today_focus'], 'today_focus')
            results['today_focus'] = today_focus

        return results

    @abstractmethod
    def run(self) -> int:
        """运行爬虫并保存到数据库，返回抓取数量"""
        pass


class GenericCrawler(BaseCrawler):
    """通用爬虫实现"""

    def run(self) -> int:
        """运行爬虫"""
        results = self.crawl()
        total_saved = 0

        for category, news_list in results.items():
            logger.info(f"{category} 抓取到 {len(news_list)} 条新闻")

            if news_list:
                saved_count = self.database.insert_news_batch(news_list)
                total_saved += saved_count
                logger.info(f"保存了 {saved_count} 条到数据库")

        return total_saved
