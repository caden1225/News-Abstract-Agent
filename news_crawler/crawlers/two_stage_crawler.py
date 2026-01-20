"""
两阶段爬虫实现（异步并行版本）
第一阶段：从TopHub获取新闻列表（标题、链接等基本信息）
第二阶段：并行访问实际新闻页面获取详细内容
"""

import json
import time
import random
import asyncio
import aiohttp
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from models.news import NewsItem
from ..database import Database
from ..logger_config import get_crawler_logger

logger = get_crawler_logger(__name__)


class TwoStageCrawler:
    """两阶段爬虫：先获取列表，再并行获取详情"""

    def __init__(self, config: Dict, database: Database):
        self.config = config
        self.database = database
        self.name = config.get('name', 'Unknown')
        self.base_url = config.get('base_url', '')
        self.encoding = config.get('encoding', 'utf-8')
        self.request_delay = config.get('request_delay', 1)

        # 并发控制
        self.max_concurrent = config.get('max_concurrent', 10)  # 最大并发请求数

        # 第二阶段配置（获取详情）
        self.detail_config = config.get('detail_config', {})

        # 同步session用于第一阶段
        import requests
        self._sync_session = None
        self._common_config = config.get('common', {})

    def _get_sync_session(self):
        """获取同步requests session"""
        if self._sync_session is None:
            import requests
            self._sync_session = requests.Session()
            self._sync_session.headers.update({
                'User-Agent': self._common_config.get(
                    'user_agent',
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
            })
        return self._sync_session

    def _parse_datetime(self, date_str: str, format_str: str = None) -> Optional[datetime]:
        """解析日期时间字符串"""
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        # 常见格式
        common_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d %H:%M',
            '%Y/%m/%d',
        ]

        if format_str:
            try:
                return datetime.strptime(date_str, format_str)
            except ValueError:
                pass

        for fmt in common_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _extract_tags_from_site_name(self) -> List[str]:
        """从站点名称中提取标签

        例如：
        - "TopHub时政频道" -> ["时政"]
        - "TopHub财经频道" -> ["财经"]
        - "TopHub科技频道" -> ["科技"]
        - "TopHub体育频道" -> ["体育"]
        - "TopHub网易热榜" -> None (不是频道类型的站点)
        """
        site_name = self.name

        # 检查是否是频道类型的站点
        if '频道' not in site_name:
            return None

        # 去掉"TopHub"前缀
        if site_name.startswith('TopHub'):
            tag_part = site_name[6:]  # 去掉"TopHub"
        else:
            tag_part = site_name

        # 去掉"频道"后缀
        if '频道' in tag_part:
            tag = tag_part.replace('频道', '')
            if tag:  # 确保标签不为空
                return [tag]

        return None

    def _fetch_news_list(self, category_config: Dict, category_name: str) -> List[Dict]:
        """第一阶段：从TopHub获取新闻列表（同步请求）"""
        if not category_config.get('enabled', False):
            return []

        url = category_config.get('url', '')
        max_items = category_config.get('max_items', 15)
        field_mapping = category_config.get('field_mapping', {})

        if not url:
            logger.warning(f"未配置URL: {category_name}")
            return []

        logger.info(f"第一阶段：抓取 [{self.name}] - {category_name}")
        logger.debug(f"URL: {url}")

        session = self._get_sync_session()
        max_retries = self._common_config.get('retry_times', 3)
        retry_delay = self._common_config.get('retry_delay', 5)

        # 同步请求
        for attempt in range(max_retries):
            try:
                response = session.get(url, timeout=30, allow_redirects=True)
                response.encoding = self.encoding
                break
            except Exception as e:
                logger.debug(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {url}, 错误: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.warning(f"请求最终失败: {url}")
                    return []

        soup = BeautifulSoup(response.text, 'html.parser')
        container_selector = field_mapping.get('container', '')

        if not container_selector:
            logger.warning("未配置容器选择器")
            return []

        items = soup.select(container_selector)
        news_list = []

        # 检查是否是表格结构（通过检查第一个元素是否有td）
        is_table_structure = False
        if items:
            first_item = items[0] if len(items) > 0 else None
            if first_item and first_item.find('td'):
                is_table_structure = True

        # 获取标题列索引配置（默认为2，即第3列）
        title_col_index = field_mapping.get('title_column_index', 2)
        # 获取图片列索引配置（默认为1，即第2列）
        image_col_index = field_mapping.get('image_column_index', 1)

        # 获取通用字段映射配置
        title_config = field_mapping.get('title', {})
        url_config = field_mapping.get('url', {})
        image_config = field_mapping.get('image_url', {})
        source_config = field_mapping.get('source', {})
        time_config = field_mapping.get('publish_time', {})

        # 跳过表头（如果是表格结构）
        start_index = 1 if is_table_structure else 0
        items_to_process = items[start_index:max_items+start_index]

        for item_element in items_to_process:
            try:
                title = ""
                news_url = ""
                image_url = ""
                source = ""
                publish_time = None

                if is_table_structure:
                    # 表格结构：使用列索引
                    tds = item_element.find_all('td')
                    if len(tds) < title_col_index + 1:
                        continue

                    # 根据配置的索引获取标题和URL
                    title_elem = tds[title_col_index].select_one('a') if len(tds) > title_col_index else None
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    news_url = title_elem.get('href', '') if title_elem else ""

                    # 根据配置获取图片（如果有的话）
                    if len(tds) > image_col_index and image_col_index >= 0:
                        image_elem = tds[image_col_index].select_one('img')
                        if image_elem:
                            image_url = image_elem.get('src', '')

                    # 尝试获取来源媒体（如果有）
                    for td in tds:
                        if td.get('class') == ['ws']:  # 来源列的class
                            source = td.get_text(strip=True)
                            break
                else:
                    # 通用列表结构：使用CSS选择器
                    if title_config:
                        selector = title_config.get('selector', '')
                        # 如果选择器为空，直接使用容器元素本身
                        if not selector:
                            title_elem = item_element
                        else:
                            title_elem = item_element.select_one(selector)
                            # 如果选择器没找到，且容器元素本身匹配选择器，使用容器本身
                            if not title_elem and item_element.name == selector.strip('.').strip('#'):
                                title_elem = item_element
                        
                        if title_elem:
                            if title_config.get('attr', 'text') == 'text':
                                title = title_elem.get_text(strip=True)
                            else:
                                title = title_elem.get(title_config.get('attr', ''), '')

                    if url_config:
                        selector = url_config.get('selector', '')
                        # 如果选择器为空，直接使用容器元素本身
                        if not selector:
                            url_elem = item_element
                        else:
                            url_elem = item_element.select_one(selector)
                            # 如果选择器没找到，且容器元素本身匹配选择器，使用容器本身
                            if not url_elem and item_element.name == selector.strip('.').strip('#'):
                                url_elem = item_element
                        
                        if url_elem:
                            if url_config.get('attr', 'href') == 'text':
                                news_url = url_elem.get_text(strip=True)
                            else:
                                news_url = url_elem.get(url_config.get('attr', 'href'), '')

                    if image_config:
                        image_elem = item_element.select_one(image_config.get('selector', ''))
                        if image_elem:
                            image_url = image_elem.get(image_config.get('attr', 'src'), '')

                    if source_config:
                        source_elem = item_element.select_one(source_config.get('selector', ''))
                        if source_elem:
                            if source_config.get('attr', 'text') == 'text':
                                source = source_elem.get_text(strip=True)
                            else:
                                source = source_elem.get(source_config.get('attr', ''), '')

                    if time_config:
                        time_elem = item_element.select_one(time_config.get('selector', ''))
                        if time_elem:
                            time_str = time_elem.get_text(strip=True) if time_config.get('attr', 'text') == 'text' else time_elem.get(time_config.get('attr', ''), '')
                            if time_str:
                                publish_time = self._parse_datetime(time_str, time_config.get('format'))

                if title and news_url:
                    # 处理相对URL
                    if news_url.startswith('/'):
                        news_url = urljoin(self.base_url, news_url)

                    # 将单个图片URL转换为列表格式
                    image_urls = [image_url] if image_url else None
                    
                    news_list.append({
                        'title': title,
                        'url': news_url,
                        'publish_time': publish_time,
                        'hot_value': '',
                        'source_site': self.name,
                        'category': category_name,
                        'image_urls': image_urls,
                        'source': source
                    })
                    logger.debug(f"  ✓ {title[:50]}...")

            except Exception as e:
                logger.debug(f"解析失败: {e}")
                continue

        # 添加延迟
        if self.request_delay > 0:
            time.sleep(self.request_delay + random.uniform(0, 1))

        logger.info(f"第一阶段完成：获取了 {len(news_list)} 条新闻链接")
        
        # 过滤掉已抓取的URL（在第一阶段就去重，避免不必要的详情页请求）
        if news_list:
            urls = [item['url'] for item in news_list]
            new_urls = self.database.filter_crawled_urls(urls)
            
            if len(new_urls) < len(urls):
                skipped_count = len(urls) - len(new_urls)
                logger.debug(f"跳过已抓取的URL: {skipped_count} 条")
                # 只保留未抓取的新闻
                news_list = [item for item in news_list if item['url'] in new_urls]
                logger.info(f"待抓取: {len(news_list)} 条")
        
        return news_list

    async def _fetch_news_detail_async(self, session: aiohttp.ClientSession, news_url: str, basic_info: Dict) -> Optional[NewsItem]:
        """第二阶段：异步获取新闻详细内容"""
        logger.debug(f"第二阶段: {basic_info['title'][:40]}...")

        try:
            # 对于中华网，尝试先访问全文页面（如果存在）
            # 检查URL是否已经是全文页面
            full_url = news_url
            if 'china.com' in news_url and not news_url.endswith('_all.html'):
                # 尝试构造全文页面URL
                # 例如: 49168530.html -> 49168530_all.html
                import re
                match = re.search(r'/(\d+)\.html$', news_url)
                if match:
                    article_id = match.group(1)
                    full_url = news_url.replace(f'{article_id}.html', f'{article_id}_all.html')
            
            # 先尝试访问全文页面
            try:
                async with session.get(full_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        html = await response.text(encoding=self.encoding)
                        soup = BeautifulSoup(html, 'html.parser')
                        # 检查是否成功获取到完整内容
                        article_content = soup.select_one('#js_article_content')
                        if article_content and len(article_content.get_text(strip=True)) > 500:
                            # 全文页面成功，使用它
                            news_url = full_url
                        else:
                            # 全文页面内容不够，回退到原URL
                            async with session.get(news_url, timeout=aiohttp.ClientTimeout(total=30)) as response2:
                                html = await response2.text(encoding=self.encoding)
                                soup = BeautifulSoup(html, 'html.parser')
                    else:
                        # 全文页面不存在，使用原URL
                        async with session.get(news_url, timeout=aiohttp.ClientTimeout(total=30)) as response2:
                            html = await response2.text(encoding=self.encoding)
                            soup = BeautifulSoup(html, 'html.parser')
            except Exception:
                # 如果访问全文页面失败，回退到原URL
                async with session.get(news_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    html = await response.text(encoding=self.encoding)
                    soup = BeautifulSoup(html, 'html.parser')

            # 尝试提取标题
            # 首先检查是否有站点特定的配置
            title_selectors = self.detail_config.get('title_selectors', [])
            if title_selectors:
                title_elem = None
                for selector in title_selectors:
                    title_elem = soup.select_one(selector)
                    if title_elem:
                        break
                title = title_elem.get_text(strip=True) if title_elem else basic_info.get('title', '')
            else:
                title_elem = soup.select_one('h1') or soup.select_one('.title') or soup.select_one('title')
                title = title_elem.get_text(strip=True) if title_elem else basic_info.get('title', '')

            # 尝试提取完整的正文内容（优先使用正文，而不是meta description）
            content = ''
            article_body = None
            
            # 尝试多个常见的选择器来找到正文区域
            # 首先检查是否有站点特定的配置
            custom_selectors = self.detail_config.get('article_selectors', [])
            has_custom_selectors = len(custom_selectors) > 0
            
            if has_custom_selectors:
                # 如果配置了自定义选择器，优先使用这些选择器
                article_selectors = custom_selectors
            else:
                # 否则使用默认选择器列表
                article_selectors = [
                    '.article-body',
                    '.post_body',
                    '.article-content',
                    '#article-content',
                    '.content',
                    'article',
                    '.article',
                    '.post-content',
                    '.news-content',
                    'main article',
                    '.main-content',
                    '.article_wrap',  # 中华网
                    '#js-info-flow',  # 中华网
                ]
            
            for selector in article_selectors:
                article_body = soup.select_one(selector)
                if article_body:
                    # 移除script、style、noscript等无关标签
                    for tag in article_body(['script', 'style', 'noscript', 'iframe', 'embed']):
                        tag.decompose()
                    
                    # 移除常见的无关元素（如广告、分享按钮等）
                    for unwanted in article_body.select('.ad, .advertisement, .share, .social-share, .comment, .related-news'):
                        unwanted.decompose()
                    
                    # 提取完整内容，使用换行符分隔段落
                    full_content = article_body.get_text(strip=True, separator='\n')
                    
                    # 如果配置了自定义选择器，直接使用找到的内容（不检查长度）
                    # 否则，只有当内容足够长（大于100字符）时才使用
                    if has_custom_selectors:
                        if full_content:
                            content = full_content
                            break
                    else:
                        if full_content and len(full_content) > 100:
                            content = full_content
                            break
            
            # 如果正文提取失败或内容太短，尝试使用meta description作为后备
            if not content or len(content) < 100:
                desc_elem = soup.select_one('meta[name="description"]')
                meta_desc = desc_elem.get('content', '') if desc_elem else ''
                if meta_desc and len(meta_desc) > len(content):
                    content = meta_desc

            # 尝试提取图片 - 从正文中获取真实新闻图片列表
            image_urls = []  # 存储所有图片URL

            # 如果找到了article_body，从中提取图片
            if article_body:
                # 网易新闻的图片在 .m-photo 标签内，真实URL在 data-echo 属性
                news_images = article_body.select('.m-photo img')
                if news_images:
                    # 获取所有新闻图片
                    for img in news_images:
                        # data-echo 属性包含真实图片URL
                        real_image_url = img.get('data-echo', '')
                        if real_image_url:
                            image_urls.append(real_image_url)
                        elif img.get('src'):
                            src = img.get('src', '')
                            # 跳过占位图
                            if 'empty.png' not in src:
                                image_urls.append(src)

                # 如果没找到.m-photo中的图片，尝试查找其他图片
                if not image_urls:
                    all_images = article_body.select('img')
                    for img in all_images:
                        src = img.get('data-echo') or img.get('src') or img.get('data-src', '')
                        if src and 'static.ws.126.net/163/frontend/images/2022/empty.png' not in src:
                            image_urls.append(src)

            # 如果正文没找到图片，尝试meta标签（但通常这是logo）
            if not image_urls:
                # 从基本信息中获取图片URL列表
                basic_image_urls = basic_info.get('image_urls', [])
                if basic_image_urls:
                    image_urls = basic_image_urls
                else:
                    og_image = soup.select_one('meta[property="og:image"]')
                    if og_image:
                        image_urls = [og_image.get('content', '')]

            # 尝试提取来源
            source = basic_info.get('source', '')
            if not source:
                # 首先检查是否有站点特定的配置
                source_selectors = self.detail_config.get('source_selectors', [])
                if source_selectors:
                    source_elem = None
                    for selector in source_selectors:
                        source_elem = soup.select_one(selector)
                        if source_elem:
                            break
                    if source_elem:
                        source = source_elem.get_text(strip=True)
                else:
                    source_elem = soup.select_one('.s-source') or soup.select_one('.source')
                    if source_elem:
                        source = source_elem.get_text(strip=True)

            # 如果还没获取到来源，使用默认值
            if not source:
                source = self.name  # 使用站点名称作为默认来源

            # 尝试提取发布时间
            publish_time = basic_info.get('publish_time')
            if not publish_time:
                # 首先检查是否有站点特定的配置
                time_selectors = self.detail_config.get('time_selectors', [])
                if time_selectors:
                    time_elem = None
                    for selector in time_selectors:
                        time_elem = soup.select_one(selector)
                        if time_elem:
                            break
                    if time_elem:
                        time_str = time_elem.get_text(strip=True) or time_elem.get('datetime', '')
                        publish_time = self._parse_datetime(time_str)
                else:
                    time_elem = soup.select_one('.s-ptime') or soup.select_one('.publish-time') or soup.select_one('time')
                    if time_elem:
                        time_str = time_elem.get_text(strip=True) or time_elem.get('datetime', '')
                        publish_time = self._parse_datetime(time_str)

            # 自动提取标签：从站点名称中去掉"TopHub"和"频道"等字眼
            tags = self._extract_tags_from_site_name()

            return NewsItem(
                title=title,
                url=news_url,
                source=source,
                source_site='TopHub',  # Always use 'TopHub' as the source site
                category=basic_info.get('category', 'hot_news'),
                tags=tags,
                publish_time=publish_time,
                image_urls=image_urls if image_urls else None,
                content=content
            )

        except Exception as e:
            logger.debug(f"获取详情失败: {e}")
            # 即使详情获取失败，也返回基本信息
            fallback_image_urls = basic_info.get('image_urls', [])
            # 即使在异常情况下，也要提取标签
            tags = self._extract_tags_from_site_name()
            return NewsItem(
                title=basic_info.get('title', ''),
                url=news_url,
                source=basic_info.get('source', '网易新闻'),
                source_site='TopHub',  # Always use 'TopHub' as the source site
                category=basic_info.get('category', 'hot_news'),
                tags=tags,
                publish_time=basic_info.get('publish_time'),
                image_urls=fallback_image_urls if fallback_image_urls else None,
                content=basic_info.get('title', '')
            )

    async def _fetch_news_details_batch(self, news_list: List[Dict]) -> List[NewsItem]:
        """批量并行获取新闻详情"""
        if not news_list:
            return []

        # 创建aiohttp session
        headers = {
            'User-Agent': self._common_config.get(
                'user_agent',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
        }

        connector = aiohttp.TCPConnector(limit=self.max_concurrent)
        timeout = aiohttp.ClientTimeout(total=30)

        logger.info(f"第二阶段：并行获取 {len(news_list)} 条新闻详细内容...")
        logger.debug(f"并发数: {self.max_concurrent}")

        async with aiohttp.ClientSession(headers=headers, connector=connector, timeout=timeout) as session:
            # 创建所有任务
            tasks = [
                self._fetch_news_detail_async(session, item['url'], item)
                for item in news_list
            ]

            # 并行执行所有任务
            detailed_news = await asyncio.gather(*tasks)

        # 过滤掉None结果
        detailed_news = [news for news in detailed_news if news is not None]
        logger.info(f"第二阶段完成：成功获取 {len(detailed_news)} 条详细新闻")

        return detailed_news

    def crawl(self) -> Dict[str, List[NewsItem]]:
        """执行两阶段爬取（异步并行版本）"""
        logger.info(f"开始两阶段爬取: {self.name}")

        results = {}

        # 第一阶段：获取新闻列表
        if 'hot_news' in self.config:
            news_list = self._fetch_news_list(self.config['hot_news'], 'hot_news')

            # 第二阶段：并行获取详细内容
            if news_list:
                detailed_news = asyncio.run(self._fetch_news_details_batch(news_list))
                results['hot_news'] = detailed_news

        # 今日关注（如果配置不同的话）
        if 'today_focus' in self.config:
            today_focus_list = self._fetch_news_list(self.config['today_focus'], 'today_focus')

            if today_focus_list:
                detailed_focus = asyncio.run(self._fetch_news_details_batch(today_focus_list))
                results['today_focus'] = detailed_focus

        return results

    def run(self) -> int:
        """运行两阶段爬虫并保存到数据库"""
        results = self.crawl()
        total_saved = 0

        for category, news_list in results.items():
            logger.info(f"{category} 获取到 {len(news_list)} 条新闻")

            if news_list:
                saved_count = self.database.insert_news_batch(news_list)
                total_saved += saved_count
                logger.info(f"保存了 {saved_count} 条到数据库")

        return total_saved
