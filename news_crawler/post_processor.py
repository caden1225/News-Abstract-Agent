"""
数据后处理模块
在数据入库前进行过滤和清理
支持通过配置文件配置正则表达式过滤规则
"""

import re
from typing import List, Optional, Dict, TYPE_CHECKING
from .logger_config import get_crawler_logger

if TYPE_CHECKING:
    from models.news import NewsItem

logger = get_crawler_logger(__name__)


class PostProcessor:
    """数据后处理器"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化后处理器
        
        Args:
            config: 配置字典，包含过滤规则——
                {
                    'filters': {
                        'content': [
                            {'pattern': r'原标题：.*', 'action': 'remove'},
                            ...
                        ],
                        'image_urls': [
                            {'pattern': r'.*empty\\.png.*', 'action': 'remove'},
                            ...
                        ],
                        'title': [
                            {'pattern': r'^原标题：', 'action': 'remove'},
                            ...
                        ]
                    }
                }
        """
        self.config = config or {}
        self.filters = self.config.get('filters', {})
        
        # 编译正则表达式以提高性能
        self.compiled_filters = self._compile_filters()
    
    def _compile_filters(self) -> Dict[str, List[Dict]]:
        """编译正则表达式"""
        compiled = {}
        
        for field, rules in self.filters.items():
            compiled[field] = []
            for rule in rules:
                pattern = rule.get('pattern', '')
                action = rule.get('action', 'remove')  # remove, replace
                replacement = rule.get('replacement', '')
                
                try:
                    compiled_rule = {
                        'pattern': re.compile(pattern, re.IGNORECASE | re.MULTILINE),
                        'action': action,
                        'replacement': replacement,
                        'description': rule.get('description', pattern)
                    }
                    compiled[field].append(compiled_rule)
                except re.error as e:
                    logger.warning(f"无效的正则表达式 [{pattern}]: {e}")
        
        return compiled
    
    def filter_content(self, content: Optional[str]) -> Optional[str]:
        """过滤正文内容"""
        if not content:
            return content
        
        result = content
        rules = self.compiled_filters.get('content', [])
        
        # 首先应用截断规则（在遇到特定标记时截断内容）
        truncate_markers = [
            r'\(责任编辑[：:]',  # 责任编辑
            r'推荐阅读',        # 推荐阅读
            r'热门文章',        # 热门文章
            r'24小时热点',      # 24小时热点
            r'^\s*[^。，！？\n]{5,50}\s*\n\s*(新华社|央视|今日头条|中国新闻网|环球时报)',  # 其他新闻标题+来源
        ]
        
        # 找到第一个截断标记的位置
        min_pos = len(result)
        for marker_pattern in truncate_markers:
            pattern = re.compile(marker_pattern, re.IGNORECASE | re.MULTILINE)
            match = pattern.search(result)
            if match:
                pos = match.start()
                if pos < min_pos:
                    min_pos = pos
        
        # 如果找到截断位置，截断内容
        if min_pos < len(result):
            result = result[:min_pos]
        
        # 应用其他过滤规则
        for rule in rules:
            if rule['action'] == 'remove':
                # 移除匹配的内容
                result = rule['pattern'].sub('', result)
            elif rule['action'] == 'replace':
                # 替换匹配的内容
                result = rule['pattern'].sub(rule['replacement'], result)
            elif rule['action'] == 'truncate':
                # 截断操作：在匹配位置截断
                match = rule['pattern'].search(result)
                if match:
                    result = result[:match.start()]
        
        # 清理多余的空行和空白
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)  # 多个空行合并为两个
        result = result.strip()
        
        return result if result else None
    
    def filter_title(self, title: str) -> str:
        """过滤标题"""
        if not title:
            return title
        
        result = title
        rules = self.compiled_filters.get('title', [])
        
        for rule in rules:
            if rule['action'] == 'remove':
                result = rule['pattern'].sub('', result)
            elif rule['action'] == 'replace':
                result = rule['pattern'].sub(rule['replacement'], result)
        
        return result.strip()
    
    def filter_image_urls(self, image_urls: Optional[List[str]]) -> Optional[List[str]]:
        """过滤图片URL列表"""
        if not image_urls:
            return image_urls
        
        rules = self.compiled_filters.get('image_urls', [])
        filtered_urls = []
        
        for url in image_urls:
            if not url:
                continue
            
            should_keep = True
            
            for rule in rules:
                if rule['pattern'].search(url):
                    if rule['action'] == 'remove':
                        should_keep = False
                        break
                    elif rule['action'] == 'replace':
                        url = rule['pattern'].sub(rule['replacement'], url)
            
            if should_keep:
                filtered_urls.append(url)
        
        return filtered_urls if filtered_urls else None

    def process(self, news: 'NewsItem') -> 'NewsItem':
        """
        处理单条新闻数据

        Args:
            news: 原始新闻数据

        Returns:
            处理后的新闻数据
        """
        # 创建副本以避免修改原始对象
        from models.news import NewsItem
        processed = NewsItem(
            id=news.id,
            title=self.filter_title(news.title),
            url=news.url,
            source=news.source,
            source_site=news.source_site,
            category=news.category,
            tags=news.tags,  # 保留标签
            publish_time=news.publish_time,
            image_urls=self.filter_image_urls(news.image_urls),
            content=self.filter_content(news.content),
            author=news.author,
            created_at=news.created_at
        )

        return processed
    
    def process_batch(self, news_list: List['NewsItem']) -> List['NewsItem']:
        """
        批量处理新闻数据
        
        Args:
            news_list: 原始新闻数据列表
            
        Returns:
            处理后的新闻数据列表
        """
        processed_list = []
        
        for news in news_list:
            processed = self.process(news)
            processed_list.append(processed)
        
        return processed_list


def create_processor_from_config(global_config: Dict, site_config: Dict) -> PostProcessor:
    """
    从配置创建后处理器
    合并全局配置和站点特定配置
    
    Args:
        global_config: 全局配置（common.post_processor）
        site_config: 站点特定配置（site.post_processor）
        
    Returns:
        PostProcessor实例
    """
    # 合并配置：站点配置优先
    merged_config = {
        'filters': {}
    }
    
    # 先应用全局配置
    if global_config:
        global_filters = global_config.get('filters', {})
        for field, rules in global_filters.items():
            merged_config['filters'][field] = rules.copy()
    
    # 再应用站点特定配置（会覆盖全局配置）
    if site_config:
        site_filters = site_config.get('filters', {})
        for field, rules in site_filters.items():
            if field in merged_config['filters']:
                # 合并规则（站点规则追加到全局规则后面）
                merged_config['filters'][field].extend(rules)
            else:
                merged_config['filters'][field] = rules.copy()
    
    return PostProcessor(merged_config)

