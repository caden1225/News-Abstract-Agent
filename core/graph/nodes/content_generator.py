"""
内容生成节点

包含新闻选择和摘要生成功能
"""
import logging
import time
import asyncio
import re
from typing import Dict, Any, List

from core.crawler_service import get_crawler_service
from prompts import build_news_summary_messages
from core.constants import DATABASE_CONFIG, WORKFLOW_CONFIG, LLM_CONFIG
from models.state import NewsAgentState

logger = logging.getLogger(__name__)


async def news_selector_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    新闻选择节点
    从获取的新闻中选择最重要的几条进行摘要
    """
    news_list = state.get("news_list", [])

    # 打印节点开始
    print("\n" + "📊" * 20)
    print("  节点 4: 新闻选择")
    print("📊" * 20)

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - 总新闻数: {len(news_list)}")

    start = time.time()

    if not news_list:
        elapsed = (time.time() - start) * 1000

        print(f"\n❌ 错误: 未找到新闻")
        update = {
            "selected_news": [],
            "image_links": [],
            "current_step": "未找到相关新闻",
            "progress_percentage": WORKFLOW_CONFIG.PROGRESS_NEWS_SELECTION,
            "processing_steps": ["❌ 未找到相关新闻"],
            "error": "未找到相关新闻"
        }

        logger.error(f"❌ 新闻选择失败: 无新闻数据")
        print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")
        return update

    # 从配置文件读取选择数量
    from llm_utils.config import config
    news_selection_config = config.get("news_selection", {})
    max_selected_news = news_selection_config.get("max_selected_news", DATABASE_CONFIG.MAX_SELECTED_NEWS)
    max_images = news_selection_config.get("max_images", DATABASE_CONFIG.MAX_IMAGES)

    print(f"\n📋 配置:")
    print(f"  - 最大选择新闻数: {max_selected_news}")
    print(f"  - 最大图片数: {max_images}")

    # 删除分类过滤逻辑，直接选择前N条
    # 注意：如果后续需要按相关性排序，可以在这里添加排序逻辑
    selected = news_list[:max_selected_news]

    print(f"\n🔍 选择结果:")
    print(f"  - 选择前: {len(news_list)} 条")
    print(f"  - 选择后: {len(selected)} 条")

    # 提取图片（保持现有逻辑）
    images = []
    for news in selected:
        if news.get("images"):
            images.extend(news["images"])

    elapsed = (time.time() - start) * 1000

    # 打印选择结果
    print(f"\n📊 选择结果:")
    print(f"  - 选中的新闻: {len(selected)} 条")
    print(f"  - 图片总数: {len(images)} 张（限制: {max_images}）")
    print(f"  - 处理耗时: {elapsed:.2f}ms")

    if selected:
        print(f"\n📰 选中的新闻:")
        for i, news in enumerate(selected, 1):
            title = news.get("title", "")
            img_count = len(news.get("images", []))
            print(f"  {i}. {title[:60]}... (图片: {img_count})")

    update = {
        "selected_news": selected,
        "image_links": images[:max_images],  # 使用配置的最大图片数
        "current_step": f"正在从{len(news_list)}条新闻中精选内容...",
        "progress_percentage": WORKFLOW_CONFIG.PROGRESS_NEWS_SELECTION,
        "processing_steps": [
            f"📊 精选重要新闻：从{len(news_list)}条中选出{len(selected)}条"
        ]
    }

    logger.info(f"✅ 新闻选择完成: selected={len(selected)}, images={len(images)}, elapsed={elapsed:.2f}ms")
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")

    return update


async def summarizer_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    摘要生成节点（支持流式生成）
    使用LLM生成新闻播报稿，支持流式输出
    """
    selected_news = state.get("selected_news", [])

    # 打印节点开始
    print("\n" + "✍️" * 20)
    print("  节点 5: 摘要生成（流式）")
    print("✍️" * 20)

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - 新闻数量: {len(selected_news)}")

    if not selected_news:
        print(f"\n❌ 错误: 无新闻内容")
        update = {
            "summary": "抱歉，未找到相关新闻内容。",
            "streaming_text": "抱歉，未找到相关新闻内容。",
            "text_ready": True,
            "current_step": "未找到新闻内容",
            "progress_percentage": WORKFLOW_CONFIG.PROGRESS_SUMMARY_GENERATION,
            "processing_steps": ["❌ 无新闻内容可摘要"]
        }
        logger.error(f"❌ 摘要生成失败: 无新闻数据")
        print(f"\n✅ 节点完成")
        return update

    print(f"\n📰 待处理的新闻:")
    for i, news in enumerate(selected_news, 1):
        title = news.get("title", "")
        print(f"  {i}. {title[:70]}")

    print(f"\n🤖 调用 LLM 生成连贯播报稿（流式）...")

    start = time.time()

    # 检查是否使用流式生成
    use_streaming = state.get("stream", False)

    # 获取目标语言（优先使用summary_target_language，如果没有则使用tts_language，默认为中文）
    target_language = state.get("summary_target_language") or state.get("tts_language", "zh")
    print(f"\n🌐 摘要目标语言: {target_language}")

    # 获取 enable_thinking 配置（从配置文件/环境变量读取）
    from llm_utils.config import config
    thinking_config = config.get_thinking_config()
    enable_thinking = thinking_config["enable_thinking"]

    print(f"\n💭 Thinking配置: enable={enable_thinking}, budget={thinking_config['thinking_budget']}")

    if use_streaming:
        # 流式生成：使用真正的流式LLM调用
        from llm_utils.llm_service import LLMService, llm_config

        messages = build_summary_messages(selected_news, target_language=target_language)
        model_name = llm_config['model']

        # 流式调用LLM（摘要生成是唯一启用thinking的地方）
        accumulated_text = ""
        thinking_content = ""

        # 注意：仅摘要生成时启用thinking，意图分析等其他节点不启用
        async for token_type, token_content in LLMService.call_llm_stream(
            model_name=model_name,
            messages=messages,
            temperature=LLM_CONFIG.SUMMARY_TEMPERATURE,
            max_tokens=LLM_CONFIG.SUMMARY_MAX_TOKENS,
            enable_thinking=enable_thinking  # 使用API参数或配置文件设置
        ):
            if token_type == "thinking":
                thinking_content += token_content
                print(token_content, end="", flush=True)  # 实时显示思考进度
            else:
                accumulated_text += token_content
                print(f".", end="", flush=True)  # 实时显示生成进度

        print()  # 换行

        # 如果流式中没有检测到 thinking，尝试从累积文本中解析 <think> 标签
        if not thinking_content and accumulated_text:
            thinking_content, accumulated_text = parse_thinking_and_summary(accumulated_text)

        summary = accumulated_text

        # 记录思维链
        thinking_step = {
            "node": "summarizer",
            "timestamp": int(time.time() * 1000),
            "thinking": thinking_content if thinking_content else "正在生成播报稿..."
        }

        elapsed = (time.time() - start) * 1000

        print(f"\n📊 生成结果:")
        print(f"  - 思考过程长度: {len(thinking_content)} 字符")
        print(f"  - 摘要长度: {len(summary)} 字符")
        print(f"  - 流式生成耗时: {elapsed:.2f}ms ({elapsed/1000:.2f}s)")

        update = {
            "summary": summary,
            "streaming_text": summary,  # 流式文本（完整内容）
            "text_ready": True,
            "thinking_chain": [thinking_step],
            # 注意：不更新 current_step 和 progress_percentage，避免与并行节点冲突
            "processing_steps": ["✍️ 生成播报稿（流式）"]
        }
    else:
        # 非流式生成
        thinking_content, summary = await generate_summary_with_llm(
            selected_news,
            enable_thinking,
            target_language=target_language
        )

        # 记录思维链
        thinking_step = {
            "node": "summarizer",
            "timestamp": int(time.time() * 1000),
            "thinking": thinking_content if thinking_content else "正在生成播报稿..."
        }

        elapsed = (time.time() - start) * 1000

        print(f"\n📊 生成结果:")
        print(f"  - 思考过程长度: {len(thinking_content)} 字符")
        print(f"  - 摘要长度: {len(summary)} 字符")
        print(f"  - 生成耗时: {elapsed:.2f}ms ({elapsed/1000:.2f}s)")

        update = {
            "summary": summary,
            "streaming_text": summary,
            "text_ready": True,
            "thinking_chain": [thinking_step],
            # 注意：不更新 current_step 和 progress_percentage，避免与并行节点冲突
            "processing_steps": ["✍️ 生成播报稿"]
        }

    print(f"\n📝 生成的播报稿:")
    print("─" * 70)
    # 打印前200字符预览
    preview = summary[:200] + "..." if len(summary) > 200 else summary
    print(preview)
    print("─" * 70)

    logger.info(f"✅ 摘要生成完成: length={len(summary)}, elapsed={elapsed:.2f}ms")
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")

    return update


def build_summary_messages(news_list: List[Dict], target_language: str = "zh") -> List[Dict[str, str]]:
    """
    构建新闻摘要的 messages（包含 system 和 user）

    使用统一的新闻摘要 Prompt 系统，根据目标语言动态生成多语言 prompt。

    Args:
        news_list: 新闻列表
        target_language: 目标语言 ("zh" 中文, "en" 英文, "ko" 韩语)

    Returns:
        LLM messages 格式: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    """
    # 使用统一的新闻摘要 prompt 系统
    return build_news_summary_messages(news_list, target_language=target_language)


async def generate_summary_with_llm(
    news_list: List[Dict],
    enable_thinking: bool = True,
    target_language: str = "zh"
) -> tuple[str, str]:
    """
    使用LLM生成新闻摘要（返回思考过程和播报稿）

    Args:
        news_list: 新闻列表
        enable_thinking: 是否启用LLM思考功能
        target_language: 目标语言 ("zh" 中文, "en" 英文, "ko" 韩语)

    Returns:
        (thinking_content, summary) 元组
    """
    from llm_utils.llm_service import LLMService, llm_config
    import os

    # 检查是否启用LLM
    use_llm = os.getenv("USE_LLM_FOR_SUMMARY", "true").lower() == "true"

    if not use_llm:
        logger.info("LLM摘要已禁用，使用简单拼接")
        summary = generate_simple_summary(news_list)
        return ("使用简单拼接方式生成摘要", summary)

    try:
        # 构建 messages（使用统一的 prompt 管理系统）
        messages = build_summary_messages(news_list, target_language=target_language)

        # 从配置获取模型名称
        model_name = llm_config['model']

        logger.info(f"调用LLM生成连贯播报稿: mode={llm_config['mode']}, model={model_name}, "
                   f"news_count={len(news_list)}, thinking={enable_thinking}")

        # 调用LLM（仅摘要生成启用thinking，提取思考内容）
        thinking_content, summary = await LLMService.call_llm_with_thinking(
            model_name=model_name,
            messages=messages,
            temperature=LLM_CONFIG.SUMMARY_TEMPERATURE,
            max_tokens=LLM_CONFIG.SUMMARY_MAX_TOKENS,
            enable_thinking=enable_thinking
        )

        # 打印调试信息
        print(f"\n💭 LLM 思考内容提取结果:")
        print(f"  - thinking_content 长度: {len(thinking_content)} 字符")
        print(f"  - summary 长度: {len(summary)} 字符")
        if thinking_content:
            print(f"  - thinking 预览: {thinking_content[:200]}...")

        logger.info(f"LLM连贯播报稿生成成功: thinking_length={len(thinking_content)}, "
                   f"summary_length={len(summary)}")
        return (thinking_content, summary)

    except Exception as e:
        logger.error(f"LLM摘要生成失败: {e}，使用简单拼接")
        summary = generate_simple_summary(news_list)
        return (f"LLM生成失败，使用简单拼接: {str(e)}", summary)


def parse_thinking_and_summary(response: str) -> tuple[str, str]:
    """
    解析模型响应，提取思考过程和播报稿

    支持多种格式：
    1. <think>...</think> 标签（模型原生格式）
    2. ### 思考过程：... ### 播报稿：... 格式
    3. 思考过程：... 播报稿：... 格式

    Args:
        response: 模型原始响应

    Returns:
        (thinking_content, summary) 元组
    """
    thinking_content = ""
    answer_content = response

    # 方式1: 解析 <think> 标签
    think_match = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
    if think_match:
        thinking_content = think_match.group(1).strip()
        # 移除思考标签后的内容作为答案
        answer_content = re.sub(r'<think>.*?</think>\s*', '', response, flags=re.DOTALL).strip()
        print(f"💭 解析到 <think> 标签: {len(thinking_content)} 字符")
        return (thinking_content, answer_content)

    # 方式2: 尝试匹配格式：### 思考过程：... ### 播报稿：...
    thinking_pattern = r'###\s*思考过程[：:]\s*(.*?)(?=###\s*播报稿|$)'
    summary_pattern = r'###\s*播报稿[：:]\s*(.*?)$'

    thinking_match = re.search(thinking_pattern, response, re.DOTALL)
    summary_match = re.search(summary_pattern, response, re.DOTALL)

    if thinking_match and summary_match:
        print(f"💭 解析到 ### 格式")
        return (thinking_match.group(1).strip(), summary_match.group(1).strip())

    # 方式3: 尝试其他格式：思考过程：... 播报稿：...
    thinking_pattern2 = r'思考过程[：:]\s*(.*?)(?=播报稿[：:]|$)'
    summary_pattern2 = r'播报稿[：:]\s*(.*?)$'

    thinking_match2 = re.search(thinking_pattern2, response, re.DOTALL)
    summary_match2 = re.search(summary_pattern2, response, re.DOTALL)

    if thinking_match2 and summary_match2:
        print(f"💭 解析到 思考过程/播报稿 格式")
        return (thinking_match2.group(1).strip(), summary_match2.group(1).strip())

    # 如果都匹配不到，假设整个响应都是播报稿，思考过程为空
    print(f"⚠️ 未检测到独立的思考内容，整个响应作为播报稿")
    return ("", response.strip())


def generate_simple_summary(news_list: List[Dict]) -> str:
    """
    生成简单的新闻摘要（降级方案）

    Args:
        news_list: 新闻列表

    Returns:
        简单拼接的摘要
    """
    summary_parts = ["各位听众好，以下是今日热点新闻："]

    for i, news in enumerate(news_list[:5], 1):
        title = news.get("title", "")
        summary_text = news.get("summary", news.get("ai_summary", ""))[:100]
        summary_parts.append(f"{i}. {title}：{summary_text}")

    summary_parts.append("以上就是今日热点新闻，感谢收听。")

    return "\n".join(summary_parts)
