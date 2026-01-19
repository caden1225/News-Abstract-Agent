"""
响应构建节点

包含TTS生成和响应构建功能
"""
import logging
import time
import asyncio
import base64
from typing import Dict, Any, List

from core.constants import TTS_CONFIG, WORKFLOW_CONFIG
from core.task_manager import get_language_task_manager
from models.state import NewsAgentState

logger = logging.getLogger(__name__)


async def tts_generator_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    TTS生成节点（支持并行和流式生成）
    可以基于原始新闻内容或摘要生成音频，支持流式输出
    """
    # 优先使用摘要，如果没有则使用原始新闻内容
    summary = state.get("summary", "")
    selected_news = state.get("selected_news", [])

    # 如果没有摘要，使用原始新闻内容生成音频
    if not summary and selected_news:
        # 构建临时文本用于TTS
        text_parts = []
        for news in selected_news[:3]:  # 只使用前3条
            title = news.get("title", "")
            summary_text = news.get("summary", news.get("ai_summary", ""))[:50]
            text_parts.append(f"{title}。{summary_text}")
        summary = "。".join(text_parts)

    # 打印节点开始
    print("\n" + "🔊" * 20)
    print("  节点 6: TTS生成（并行流式）")
    print("🔊" * 20)

    # 获取TTS语言配置（优先使用summary_target_language）
    request_id = state.get("request_id", "")
    llm_language_pending = state.get("llm_language_pending", False)
    tts_language = state.get("summary_target_language") or state.get("tts_language", "zh")
    language_confidence = state.get("language_confidence", 0.5)

    # 如果LLM语言判断还在执行中，等待其完成
    if llm_language_pending:
        task_manager = get_language_task_manager()
        logger.info(f"等待LLM语言判断完成: request_id={request_id}")
        print(f"\n⏳ 等待LLM语言判断完成...")

        try:
            # 等待LLM任务完成（使用配置的超时时间）
            llm_result = await task_manager.wait_for_task(
                request_id,
                timeout=WORKFLOW_CONFIG.LLM_LANGUAGE_TIMEOUT
            )

            tts_language = llm_result.get("summary_target_language") or llm_result.get("tts_language", "zh")
            language_confidence = llm_result.get("language_confidence", 0.8)

            logger.info(f"LLM语言判断完成: tts_language={tts_language}, confidence={language_confidence}")
            print(f"✅ LLM语言判断完成: {tts_language} (置信度: {language_confidence:.2f})")

        except Exception as e:
            logger.warning(f"LLM语言判断失败: {e}，使用规则结果")
            print(f"⚠️  LLM语言判断失败，使用规则结果")
    else:
        logger.info(f"LLM语言判断已完成或未启动，使用当前结果: tts_language={tts_language}")

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - 摘要长度: {len(summary)} 字符")
    print(f"  - TTS语言: {tts_language} (置信度: {language_confidence:.2f})")
    print(f"  - 并行模式: {'是' if not state.get('summary') else '否（等待摘要）'}")

    start = time.time()

    if not summary:
        elapsed = (time.time() - start) * 1000

        print(f"\n⚠️  警告: 无内容可合成")
        update = {
            "audio_data": None,
            "streaming_audio_chunks": [],
            "audio_ready": True,
            "current_step": "无内容可合成",
            "progress_percentage": WORKFLOW_CONFIG.PROGRESS_TTS_GENERATION,
            "processing_steps": ["❌ 无内容可合成语音"]
        }

        logger.warning(f"⚠️  TTS生成失败: 无内容")
        print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")
        return update

    print(f"\n🎵 生成语音播报（流式）...")
    print(f"  - 使用 Mock TTS 服务")
    print(f"  - TTS语言: {tts_language}")
    print(f"  - 音频格式: PCM (单声道 {TTS_CONFIG.AUDIO_SAMPLE_RATE}Hz)")

    # 检查是否使用流式生成
    use_streaming = state.get("stream", False)

    if use_streaming:
        # 流式生成：模拟逐块生成音频
        chunk_size = max(
            TTS_CONFIG.MIN_CHUNK_SIZE,
            len(summary) // TTS_CONFIG.CHUNK_DIVISOR
        )
        audio_chunks = []

        for i in range(0, len(summary), chunk_size):
            chunk_text = summary[i:i+chunk_size]
            # 模拟生成音频块（实际应用中调用TTS服务，返回PCM格式，单声道24000Hz）
            mock_chunk = base64.b64encode(
                f"RIFF_CHUNK_{i}_{len(chunk_text)}".encode()
            ).decode("utf-8")
            audio_chunks.append(mock_chunk)

            # 模拟生成延迟
            await asyncio.sleep(0.05)

        # 合并所有音频块
        mock_audio = base64.b64encode(
            b"RIFF" + b"_".join([chunk.encode() for chunk in audio_chunks[:5]])
        ).decode("utf-8")

        elapsed = (time.time() - start) * 1000

        print(f"\n📊 生成结果:")
        print(f"  - 音频块数: {len(audio_chunks)}")
        print(f"  - 音频数据: Mock (base64, 流式, PCM格式)")
        print(f"  - 数据长度: {len(mock_audio)} 字符")
        print(f"  - 流式生成耗时: {elapsed:.2f}ms")

        update = {
            "audio_data": mock_audio,
            "streaming_audio_chunks": audio_chunks,
            "audio_ready": True,
            "tts_language": tts_language,  # 保留语言信息
            "language_confidence": language_confidence,
            "llm_language_ready": True,  # 标记为已完成
            # 注意：不更新 current_step 和 progress_percentage，避免与并行节点冲突
            "processing_steps": [f"🔊 生成语音播报（流式，语言: {tts_language}）"]
        }
    else:
        # 非流式生成
        # 注意：这是 PCM 格式的 mock 数据（单声道 24000Hz）
        mock_audio = base64.b64encode(b"RIFF\x24\x00\x00\x00WAVE").decode("utf-8")
        elapsed = (time.time() - start) * 1000

        print(f"\n📊 生成结果:")
        print(f"  - 音频数据: Mock (base64, PCM格式)")
        print(f"  - 数据长度: {len(mock_audio)} 字符")
        print(f"  - 处理耗时: {elapsed:.2f}ms")

        update = {
            "audio_data": mock_audio,
            "streaming_audio_chunks": [mock_audio],
            "tts_language": tts_language,  # 保留语言信息
            "language_confidence": language_confidence,
            "llm_language_ready": True,  # 标记为已完成
            "audio_ready": True,
            # 注意：不更新 current_step 和 progress_percentage，避免与并行节点冲突
            "processing_steps": [f"🔊 生成语音播报（语言: {tts_language}）"]
        }

    logger.info(f"✅ TTS生成完成: mock_data, chunks={len(update.get('streaming_audio_chunks', []))}, "
               f"elapsed={elapsed:.2f}ms")
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")

    return update


async def parallel_start_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    并行启动节点
    初始化并行生成状态，准备同时启动文本和音频生成

    注意：在 LangGraph 中，真正的并行需要通过让两个节点都从同一个源出发来实现
    这个节点只是初始化状态，实际的并行执行由工作流图结构决定
    """
    # 打印节点开始
    print("\n" + "🚀" * 20)
    print("  节点 5b: 并行启动（文本 + 音频）")
    print("🚀" * 20)

    selected_news = state.get("selected_news", [])

    print(f"📥 输入状态:")
    print(f"  - 新闻数量: {len(selected_news)}")
    print(f"  - 并行模式: 文本和音频将同时生成")

    start = time.time()

    # 初始化并行状态
    update = {
        "text_ready": False,
        "audio_ready": False,
        "streaming_text": "",
        "streaming_audio_chunks": [],
        "current_step": "正在并行生成文本和音频...",
        "progress_percentage": 60,
        "processing_steps": ["🚀 启动并行生成：文本和音频"]
    }

    elapsed = (time.time() - start) * 1000

    logger.info(f"✅ 并行启动完成: elapsed={elapsed:.2f}ms")
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")
    print(f"📌 注意：文本和音频生成节点将从这里并行启动")

    return update


async def parallel_join_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    并行结果合并节点
    等待文本和音频生成都完成后，合并结果
    """
    # 打印节点开始
    print("\n" + "🔗" * 20)
    print("  节点 6b: 并行结果合并")
    print("🔗" * 20)

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - 文本就绪: {state.get('text_ready', False)}")
    print(f"  - 音频就绪: {state.get('audio_ready', False)}")
    print(f"  - 摘要长度: {len(state.get('summary', ''))} 字符")
    print(f"  - 音频块数: {len(state.get('streaming_audio_chunks', []))}")

    start = time.time()

    # 检查两个并行任务是否都完成
    text_ready = state.get("text_ready", False)
    audio_ready = state.get("audio_ready", False)

    if not text_ready or not audio_ready:
        print(f"\n⚠️  警告: 并行任务未全部完成")
        print(f"  - 文本: {'✅' if text_ready else '⏳'}")
        print(f"  - 音频: {'✅' if audio_ready else '⏳'}")

    elapsed = (time.time() - start) * 1000

    print(f"\n📊 合并结果:")
    print(f"  - 文本状态: {'✅ 完成' if text_ready else '❌ 未完成'}")
    print(f"  - 音频状态: {'✅ 完成' if audio_ready else '❌ 未完成'}")
    print(f"  - 合并耗时: {elapsed:.2f}ms")

    update = {
        "current_step": "正在合并并行生成结果...",
        "progress_percentage": 95,
        "processing_steps": ["🔗 合并文本和音频结果"]
    }

    logger.info(f"✅ 并行结果合并完成: text_ready={text_ready}, audio_ready={audio_ready}, "
               f"elapsed={elapsed:.2f}ms")
    print(f"\n✅ 节点完成，耗时: {elapsed:.2f}ms")

    return update


async def response_builder_node(state: NewsAgentState) -> Dict[str, Any]:
    """
    响应构建节点
    准备最终响应数据
    """
    # 打印节点开始
    print("\n" + "📤" * 20)
    print("  节点 7: 响应构建")
    print("📤" * 20)

    # 输入状态
    print(f"📥 输入状态:")
    print(f"  - 摘要长度: {len(state.get('summary', ''))} 字符")
    print(f"  - 新闻数量: {state.get('news_count', 0)}")
    print(f"  - 图片数量: {len(state.get('image_links', []))}")
    print(f"  - 音频数据: {'有' if state.get('audio_data') else '无'}")
    print(f"  - 进度: {state.get('progress_percentage', 0)}%")

    start = time.time()

    # 统计信息
    processing_steps = state.get("processing_steps", [])

    print(f"\n📊 处理步骤总结:")
    for i, step in enumerate(processing_steps, 1):
        print(f"  {i}. {step}")

    elapsed = (time.time() - start) * 1000

    update = {
        "current_step": "准备返回结果...",
        "progress_percentage": WORKFLOW_CONFIG.PROGRESS_COMPLETE,
        "processing_steps": ["✅ 处理完成"],
        "completed": True
    }

    logger.info(f"✅ 响应构建完成: elapsed={elapsed:.2f}ms")

    print(f"\n✅ 所有节点执行完成！")
    print(f"✅ 节点完成，耗时: {elapsed:.2f}ms")

    # 打印最终摘要
    summary = state.get("summary", "")
    if summary:
        print(f"\n" + "🎙️" * 20)
        print("  最终播报稿")
        print("🎙️" * 20)
        print("─" * 70)
        print(summary)
        print("─" * 70)

    return update
