"""
数据库操作单元测试
"""
import pytest
import tempfile
import os
from news_crawler.database import Database
from models.news import NewsItem
from datetime import datetime


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    db = Database(db_path=db_path)
    yield db
    
    # 清理
    try:
        os.unlink(db_path)
    except:
        pass


def test_database_init(temp_db):
    """测试数据库初始化"""
    conn = temp_db.get_connection()
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='news'")
    assert cursor.fetchone() is not None


def test_insert_news(temp_db):
    """测试插入新闻"""
    news = NewsItem(
        title="测试新闻",
        url="https://example.com/news/1",
        source="测试来源",
        source_site="test",
        category="hot_news",
        content="这是一条测试新闻内容，长度超过20字以满足要求。",
        publish_time=datetime.now()
    )
    
    news_id = temp_db.insert_news(news)
    assert news_id > 0


def test_get_news_by_category(temp_db):
    """测试按分类获取新闻"""
    # 插入测试数据
    news = NewsItem(
        title="测试新闻",
        url="https://example.com/news/1",
        source="测试来源",
        source_site="test",
        category="hot_news",
        content="这是一条测试新闻内容，长度超过20字以满足要求。",
        publish_time=datetime.now()
    )
    temp_db.insert_news(news)
    
    # 查询
    news_list = temp_db.get_news_by_category("hot_news", limit=10)
    assert len(news_list) > 0
    assert news_list[0].category == "hot_news"
