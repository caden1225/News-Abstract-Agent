"""
新闻抓取模块
支持多种新闻源的热点新闻抓取
"""
import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class NewsItem:
    """新闻条目"""

    def __init__(self, title: str, link: str, summary: str, published: Optional[str] = None, source: str = ""):
        self.title = title
        self.link = link
        self.summary = summary
        self.published = published
        self.source = source

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "title": self.title,
            "link": self.link,
            "summary": self.summary,
            "published": self.published,
            "source": self.source
        }


class NewsScraper:
    """新闻抓取器"""

    # 热点新闻RSS源列表
    RSS_SOURCES = {
        "百度新闻": "https://news.baidu.com/ns?word=&tn=news&rtt=1&bsst=1&cl=2&xref=http://www.baidu.com",
        "新浪新闻": "https://news.sina.com.cn/sroll/index.shtml",
        "网易新闻": "http://news.163.com/special/0001386I/ranking_news.xml",
        "头条RSS": "https://www.toutiao.com/rss/news/",
        "中国新闻网": "http://www.chinanews.com/rss/rss_focu.xml",
    }

    def __init__(self):
        self.timeout = 10

    def fetch_rss_news(self, url: str, source_name: str, limit: int = 10) -> List[NewsItem]:
        """
        从RSS源获取新闻

        Args:
            url: RSS源地址
            source_name: 新闻源名称
            limit: 最多获取新闻数量

        Returns:
            新闻列表
        """
        try:
            feed = feedparser.parse(url)
            news_items = []

            for entry in feed.entries[:limit]:
                # 获取发布时间,过滤当天新闻
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_datetime = datetime(*entry.published_parsed[:6])
                    published = published_datetime.strftime("%Y-%m-%d %H:%M:%S")

                # 创建新闻条目
                item = NewsItem(
                    title=entry.get('title', '无标题'),
                    link=entry.get('link', ''),
                    summary=entry.get('summary', entry.get('description', ''))[:500],  # 限制摘要长度
                    published=published,
                    source=source_name
                )
                news_items.append(item)

            logger.info(f"从 {source_name} 获取到 {len(news_items)} 条新闻")
            return news_items

        except Exception as e:
            logger.error(f"从 {source_name} 抓取新闻失败: {e}")
            return []

    def fetch_today_news(self, limit_per_source: int = 5) -> List[NewsItem]:
        """
        抓取当天的热点新闻

        Args:
            limit_per_source: 每个源最多获取新闻数量

        Returns:
            当天热点新闻列表
        """
        all_news = []
        today = datetime.now().date()

        for source_name, url in self.RSS_SOURCES.items():
            try:
                news_list = self.fetch_rss_news(url, source_name, limit_per_source)

                # 过滤当天的新闻
                for news in news_list:
                    if news.published:
                        try:
                            pub_date = datetime.strptime(news.published, "%Y-%m-%d %H:%M:%S").date()
                            if pub_date == today:
                                all_news.append(news)
                        except:
                            # 如果解析时间失败,仍然包含这条新闻
                            all_news.append(news)
                    else:
                        # 没有发布时间,仍然包含
                        all_news.append(news)

            except Exception as e:
                logger.error(f"处理 {source_name} 时出错: {e}")
                continue

        # 如果没有获取到新闻,返回演示数据
        if not all_news:
            logger.warning("未获取到真实新闻,返回演示数据")
            all_news = self._get_demo_news()

        # 按发布时间排序(如果有)
        all_news.sort(key=lambda x: x.published or '', reverse=True)

        logger.info(f"总共获取到 {len(all_news)} 条当天热点新闻")
        return all_news

    def _get_demo_news(self) -> List[NewsItem]:
        """
        获取演示新闻数据(当真实新闻源不可用时使用)
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        demo_news = [
            NewsItem(
                title="人工智能技术在医疗领域取得新突破",
                link="https://example.com/news1",
                summary="最新研究显示,AI辅助诊断系统在早期癌症筛查中准确率达到95%,较传统方法提升20%。该技术已在国内多家三甲医院试点应用。",
                published=now,
                source="演示新闻"
            ),
            NewsItem(
                title="全球新能源汽车销量持续增长",
                link="https://example.com/news2",
                summary="据最新统计,今年前三季度全球新能源汽车销量同比增长35%,中国市场贡献最大。专家预测全年销量有望突破1200万辆。",
                published=now,
                source="演示新闻"
            ),
            NewsItem(
                title="我国成功发射新型通信卫星",
                link="https://example.com/news3",
                summary="今日上午,我国在西昌卫星发射中心成功将一颗新型通信卫星送入预定轨道。该卫星将大幅提升偏远地区通信覆盖能力。",
                published=now,
                source="演示新闻"
            ),
            NewsItem(
                title="量子计算机研发获得重大进展",
                link="https://example.com/news4",
                summary="科研团队成功研制出50量子比特的超导量子计算机,在特定算法上的运算速度比传统计算机快1000万倍。",
                published=now,
                source="演示新闻"
            ),
            NewsItem(
                title="教育数字化转型加速推进",
                link="https://example.com/news5",
                summary="教育部发布新政策,要求全国中小学在三年内完成智慧校园建设。AI助教、虚拟实验室等新技术将逐步普及。",
                published=now,
                source="演示新闻"
            )
        ]
        return demo_news

    def fetch_hot_search_news(self) -> List[Dict]:
        """
        获取热搜新闻(简化版,返回模拟数据)

        实际生产环境中可以接入:
        - 微博热搜API
        - 百度热搜API
        - 抖音热点API
        """
        # 这里返回一个简化版本的热搜列表
        # 实际项目中应该调用真实的热搜API
        hot_topics = [
            {"title": "今日热点新闻1", "rank": 1, "heat": 1000000},
            {"title": "今日热点新闻2", "rank": 2, "heat": 950000},
            {"title": "今日热点新闻3", "rank": 3, "heat": 900000},
        ]

        return hot_topics


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = NewsScraper()
    news = scraper.fetch_today_news(limit_per_source=3)
    for item in news[:5]:
        print(f"[{item.source}] {item.title}")
        print(f"  {item.summary[:100]}...")
        print()
