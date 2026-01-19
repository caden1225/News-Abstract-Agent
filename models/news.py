"""
新闻相关数据模型
"""
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime


@dataclass
class NewsItem:
    """新闻数据模型"""
    id: Optional[int] = None
    title: str = ""
    url: str = ""
    source: str = ""  # 来源媒体
    source_site: str = ""  # 来源站点名称
    category: str = ""  # 分类：hot_news/today_focus
    tags: Optional[List[str]] = None  # 标签列表（JSON格式存储）
    publish_time: Optional[datetime] = None
    image_urls: Optional[List[str]] = None  # 多图片列表
    content: Optional[str] = None  # 新闻正文内容
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    
    @property
    def primary_image_url(self) -> Optional[str]:
        """获取主图片URL（image_urls的第一个）"""
        if self.image_urls and len(self.image_urls) > 0:
            return self.image_urls[0]
        return None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'source': self.source,
            'source_site': self.source_site,
            'category': self.category,
            'tags': self.tags,
            'publish_time': self.publish_time.isoformat() if self.publish_time else None,
            'image_urls': self.image_urls,
            'content': self.content,
            'author': self.author,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

