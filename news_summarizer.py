"""
新闻摘要模块
使用大语言模型生成新闻摘要（通过 Sidecar）
"""
import logging
from typing import List, Dict
from llm_utils.llm_service import LLMService
from llm_utils.config import config

logger = logging.getLogger(__name__)


class NewsSummarizer:
    """新闻摘要生成器 - 通过 Sidecar 调用 LLM"""

    def __init__(self):
        """
        初始化摘要生成器
        从配置文件读取模型别名
        """
        # 从配置读取模型别名
        self.model_alias = config.get("llm.summarizer_model", "qwen2-7b")
        logger.info(f"NewsSummarizer initialized with model: {self.model_alias}")

    async def summarize_single_news(self, news_item: Dict) -> str:
        """
        为单条新闻生成摘要

        Args:
            news_item: 新闻条目字典,包含title, summary, link等字段

        Returns:
            摘要文本
        """
        try:
            # 构建提示词
            prompt = f"""请为以下新闻生成一个简洁的摘要(不超过100字):

标题: {news_item.get('title', '')}
内容: {news_item.get('summary', '')}

要求:
1. 提取关键信息
2. 语言简洁明了
3. 字数控制在100字以内
"""

            messages = [
                {"role": "system", "content": "你是一个专业的新闻编辑,擅长生成简洁准确的新闻摘要。"},
                {"role": "user", "content": prompt}
            ]

            # 通过 LLMService 调用 Sidecar
            summary = await LLMService.call_llm(
                model_name=self.model_alias,
                messages=messages,
                temperature=0.7,
                max_tokens=200
            )

            logger.info(f"Summary generated for: {news_item.get('title', '')[:50]}")
            return summary.strip()

        except Exception as e:
            logger.error(f"Summarization failed: {e}", exc_info=True)
            # 降级处理:返回原始摘要的前100字
            original_summary = news_item.get('summary', '')
            return original_summary[:100] if original_summary else "暂无摘要"

    async def summarize_news_batch(self, news_list: List[Dict]) -> List[Dict]:
        """
        批量生成新闻摘要

        Args:
            news_list: 新闻列表

        Returns:
            带摘要的新闻列表
        """
        results = []
        for news_item in news_list:
            summary = await self.summarize_single_news(news_item)
            news_item['ai_summary'] = summary
            results.append(news_item)

        logger.info(f"批量生成摘要完成,共 {len(results)} 条新闻")
        return results

    async def generate_news_report(self, news_list: List[Dict]) -> str:
        """
        生成新闻播报稿

        Args:
            news_list: 新闻列表

        Returns:
            播报稿文本
        """
        try:
            # 选择前5条重要新闻
            top_news = news_list[:5]

            # 构建播报稿提示词
            prompt = "请根据以下今日热点新闻,生成一份新闻播报稿:\n\n"

            for i, news in enumerate(top_news, 1):
                ai_summary = news.get('ai_summary', news.get('summary', ''))[:100]
                prompt += f"{i}. {news.get('title', '')}\n{ai_summary}\n\n"

            prompt += """
要求:
1. 以"各位听众好,以下是今日热点新闻"开场
2. 每条新闻用简洁的语言播报
3. 条理清晰,过渡自然
4. 以"以上就是今日热点新闻,感谢收听"结束
5. 总字数控制在300字以内
"""

            messages = [
                {"role": "system", "content": "你是一个专业的新闻主播,擅长播报热点新闻。"},
                {"role": "user", "content": prompt}
            ]

            # 通过 LLMService 调用 Sidecar 生成播报稿
            report = await LLMService.call_llm(
                model_name=self.model_alias,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )

            logger.info("News report generated successfully")
            return report.strip()

        except Exception as e:
            logger.error(f"Report generation failed: {e}", exc_info=True)
            # 降级处理:简单的新闻列表
            report_parts = ["各位听众好,以下是今日热点新闻:"]
            for i, news in enumerate(news_list[:5], 1):
                report_parts.append(f"{i}. {news.get('title', '')}")
            report_parts.append("以上就是今日热点新闻,感谢收听")
            return "\n".join(report_parts)


# 测试代码
if __name__ == "__main__":
    import asyncio

    async def test():
        summarizer = NewsSummarizer()
        test_news = {
            "title": "测试新闻标题",
            "summary": "这是一条测试新闻的内容,包含了重要的信息点。",
            "link": "http://test.com"
        }
        summary = await summarizer.summarize_single_news(test_news)
        print(f"摘要: {summary}")

    asyncio.run(test())
