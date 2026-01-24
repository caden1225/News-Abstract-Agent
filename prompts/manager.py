"""
改进的 Prompt 管理系统

使用 Python 模块管理 prompt 模板，支持：
- 外部 .py 文件管理 prompt 模板
- 每个模块包含 SYSTEM_PROMPT 和 USER_PROMPT
- 使用 str.format() 进行占位符替换
- 版本管理
- 热重载
"""
import os
import re
import importlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Prompt 管理器

    特性：
    1. 从外部文件加载 prompt 模板
    2. 使用 str.format() 进行占位符替换
    3. 支持版本管理（通过文件名区分）
    4. 支持热重载
    5. 提供 preivew 和测试工具
    """

    def __init__(self, templates_dir: Optional[str] = None):
        """
        初始化 Prompt 管理器

        Args:
            templates_dir: 模板目录路径，默认为 prompts/templates
        """
        if templates_dir is None:
            # 默认模板目录
            current_dir = Path(__file__).parent
            templates_dir = current_dir / "templates"

        self.templates_dir = Path(templates_dir)

        # 缓存已加载的模板
        self._template_cache: Dict[str, str] = {}

        logger.info(f"PromptManager 初始化: templates_dir={self.templates_dir}")

    def _load_template(self, template_name: str, version: str = "default") -> Dict[str, str]:
        """
        加载 Python 模块，获取 SYSTEM_PROMPT 和 USER_PROMPT

        Args:
            template_name: 模板名称（如 "news_summary"）
            version: 版本标识（默认 "default"）

        Returns:
            包含 system 和 user 两部分的字典: {"system": str, "user": str}
        """
        # 构建模块名称
        if version == "default":
            module_name = f"prompts.templates.{template_name}"
        else:
            module_name = f"prompts.templates.{template_name}_{version}"

        try:
            # 导入模块
            module = importlib.import_module(module_name)

            # 获取 SYSTEM_PROMPT 和 USER_PROMPT
            system_prompt = getattr(module, "SYSTEM_PROMPT", "")
            user_prompt = getattr(module, "USER_PROMPT", "")

            if not user_prompt:
                raise ValueError(f"模块 {module_name} 缺少 USER_PROMPT")

            logger.debug(f"加载模板: {module_name}")
            return {"system": system_prompt, "user": user_prompt}

        except ModuleNotFoundError as e:
            raise FileNotFoundError(f"模板模块不存在: {module_name}") from e
        except Exception as e:
            raise ValueError(f"加载模板失败: {module_name}, 错误: {e}") from e

    def render_template(
        self,
        template_name: str,
        **kwargs
    ) -> Dict[str, str]:
        """
        渲染模板（system 和 user 两部分）

        Args:
            template_name: 模板名称
            **kwargs: 模板变量

        Returns:
            包含渲染后 system 和 user 的字典: {"system": str, "user": str}
        """
        # 从 kwargs 中获取 version
        version = kwargs.pop('version', 'default')

        # 加载模板
        template_parts = self._load_template(template_name, version)

        # 使用 str.format() 替换占位符
        try:
            rendered_system = template_parts["system"].format(**kwargs) if template_parts["system"] else ""
            rendered_user = template_parts["user"].format(**kwargs)
        except KeyError as e:
            raise ValueError(f"模板变量缺失: {e}")
        except Exception as e:
            raise ValueError(f"模板渲染失败: {e}")

        return {"system": rendered_system, "user": rendered_user}

    def render_messages(
        self,
        template_name: str,
        **kwargs
    ) -> List[Dict[str, str]]:
        """
        渲染模板并返回 LLM messages 格式

        Args:
            template_name: 模板名称
            **kwargs: 模板变量

        Returns:
            LLM messages 格式: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        """
        rendered = self.render_template(template_name, **kwargs)
        messages = []

        if rendered["system"]:
            messages.append({"role": "system", "content": rendered["system"]})

        messages.append({"role": "user", "content": rendered["user"]})

        return messages

    def clear_cache(self):
        """清空模板缓存"""
        self._template_cache.clear()
        logger.info("已清空模板缓存")

    def list_templates(self) -> List[str]:
        """
        列出所有可用的模板

        Returns:
            模板名称列表
        """
        templates = []
        for file_path in self.templates_dir.glob("*.py"):
            # 跳过 __init__.py 等特殊文件
            if file_path.name.startswith("__"):
                continue
            # 移除 .py 后缀
            name = file_path.stem
            templates.append(name)

        return sorted(templates)


# ==================== 文本处理工具函数 ====================

def clean_news_text(text: str) -> str:
    """
    清洗新闻文本，移除无关内容

    Args:
        text: 原始新闻文本

    Returns:
        清洗后的文本
    """
    if not text:
        return ""

    # 需要移除的无关内容模式
    patterns_to_remove = [
        r"打开网易新闻\s*查看更多图片",
        r"打开网易新闻\s*查看更多视频",
        r"打开网易新闻\s*查看更多",
        r"打开.*查看更多",
        r"查看更多图片",
        r"查看更多视频",
        r"图：.*",
        r"文\s*\|\s*[^\n]+",  # 移除"文 | 作者名"这样的格式
        r"打开.*新闻",
    ]

    cleaned_text = text

    # 移除所有匹配的模式
    for pattern in patterns_to_remove:
        cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE)

    # 移除多余的空行和空白字符
    lines = cleaned_text.split("\n")
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        # 跳过空行和过短的行（可能是无关内容）
        if line and len(line) > 3:
            cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)

    # 移除首尾空白
    cleaned_text = cleaned_text.strip()

    return cleaned_text


def format_news_items(
    news_list: List[Dict[str, Any]],
    max_count: int = 5,
    max_total_chars: int = 10_000,
) -> str:
    """
    格式化新闻列表为模板所需的字符串

    Args:
        news_list: 新闻列表
        max_count: 最多处理多少条新闻
        max_total_chars: 汇总后的新闻内容（标题+正文）的最大总字数上限，
                         超过该上限则不再追加新的新闻
    """
    items: List[str] = []
    total_chars = 0

    for i, news in enumerate(news_list[:max_count], 1):
        title = news.get("title", "")
        # 优先使用 summary，其次 ai_summary
        summary_text = news.get("summary") or news.get("ai_summary", "")

        # 清洗文本
        summary_text = clean_news_text(summary_text)

        # 限制单条长度
        if len(summary_text) > 300:
            summary_text = summary_text[:300] + "..."
        
        item_str = f"【新闻{i}】\n标题：{title}\n内容：{summary_text}"

        # 如果再追加本条会导致总字数超过上限，则停止追加新的新闻
        if total_chars + len(item_str) > max_total_chars:
            break

        items.append(item_str)
        total_chars += len(item_str)

    return "\n".join(items)




# ==================== 便捷函数 ====================

# 全局 PromptManager 实例
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """
    获取全局 PromptManager 实例

    Returns:
        PromptManager 实例
    """
    global _prompt_manager

    if _prompt_manager is None:
        _prompt_manager = PromptManager()

    return _prompt_manager


def build_news_summary_messages(
    news_list: List[Dict[str, Any]],
    target_language: str = "zh"
) -> List[Dict[str, str]]:
    """
    构建新闻摘要 messages（包含 system 和 user）

    统一使用中文prompt，但在prompt中明确要求用目标语言生成摘要。

    Args:
        news_list: 新闻列表
        target_language: 目标语言 ("zh" 中文, "en" 英文, "ko" 韩语)

    Returns:
        LLM messages 格式: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    """
    # 动态导入模板（统一使用中文prompt）
    try:
        from prompts.templates.news_summary import get_system_prompt, get_user_prompt
    except ImportError:
        logger.error("news_summary 模板不可用")
        raise

    # 格式化新闻数据
    news_items = format_news_items(news_list)

    # 构建消息（system prompt统一使用中文，user prompt也是中文但要求用目标语言生成）
    messages = [
        {
            "role": "system",
            "content": get_system_prompt()  # 统一使用中文system prompt
        },
        {
            "role": "user",
            "content": get_user_prompt(target_language).format(news_items=news_items)  # 中文prompt，但要求用目标语言生成
        }
    ]

    logger.info(f"使用中文prompt构建消息（目标语言: {target_language}）, news_count={len(news_list)}")
    return messages


def build_intent_analysis_prompt(query: str) -> str:
    """
    构建意图分析 prompt（使用外部模板）

    Args:
        query: 用户查询文本

    Returns:
        渲染后的 intent analysis prompt（字符串）
    """
    manager = get_prompt_manager()

    # 计算日期
    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 渲染模板（返回 {"system": str, "user": str}）
    rendered = manager.render_template(
        "intent_analysis",
        query=query,
        today=today,
        yesterday=yesterday
    )

    # 返回 user 部分的字符串（intent_analysis 模板的 system 为空，只需要 user）
    return rendered["user"]


