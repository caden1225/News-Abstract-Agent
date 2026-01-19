"""
新闻爬虫模块
提供统一的爬虫接口供主项目调用
"""
import os
from pathlib import Path

# 获取项目根目录（向上两级：news_crawler -> 项目根）
_PROJECT_ROOT = Path(__file__).parent.parent

# 默认配置路径（相对于项目根目录）
DEFAULT_CONFIG_PATH = str(_PROJECT_ROOT / "config" / "sites.yaml")
DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "news.db")

from .client import NewsCrawlerAPI
from .database import Database
from models.news import NewsItem

__all__ = ["NewsCrawlerAPI", "DEFAULT_CONFIG_PATH", "DEFAULT_DB_PATH", "Database", "NewsItem"]

