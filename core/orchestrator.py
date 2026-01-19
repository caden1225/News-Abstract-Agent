"""
新闻Agent主编排器
整合LangGraph工作流和流式输出

支持两种模式：
1. 非流式模式：使用完整 LangGraph 工作流
2. 流式模式（混合架构）：
   - 前置处理使用 LangGraph ainvoke
   - 流式生成（LLM + TTS）手动处理，实现真正的 token 级别流式
"""
import time
import asyncio
import base64
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional

from core.graph.workflow import build_news_workflow, build_preprocessing_workflow
from models.state import NewsAgentState
from prompts import build_news_summary_messages
from models.api import BaseResponse, ResponseData, FramePart, FramePartAudio, FramePartImage
from core.utils import (
    extract_debug_info_from_system_agent,
    merge_debug_info,
    build_debug_info_from_state
)
from llm_utils.config import config

logger = logging.getLogger(__name__)


class NewsAgentOrchestrator:
    """新闻Agent主编排器"""

    def __init__(self):
        """初始化编排器"""
        # 完整工作流（非流式模式）
        self.workflow = build_news_workflow()
        # 前置处理工作流（流式模式）
        self.preprocessing_workflow = build_preprocessing_workflow()

        # TTS模型预热（方案B优化：降低首次请求延迟）
        self._tts_warmed_up = False

        logger.info("NewsAgentOrchestrator 初始化完成")

    async def _warmup_tts_if_needed(self):
        """如果需要，预热TTS模型（方案B优化）"""
        if self._tts_warmed_up:
            return

        enable_warmup = config.get("tts.orchestrator.enable_warmup", "true").lower() in ("true", "1", "yes")
        if not enable_warmup:
            logger.info("TTS模型预热已禁用，跳过")
            self._tts_warmed_up = True
            return

        try:
            from tts_utils import get_tts_service
            tts_service = get_tts_service()

            if not tts_service or not tts_service.enabled:
                logger.info("TTS服务未启用，跳过预热")
                self._tts_warmed_up = True
                return

            warmup_timeout = float(config.get("tts.orchestrator.warmup_timeout", 15.0))
            logger.info(f"开始预热TTS模型（超时: {warmup_timeout}秒）...")

            start_time = time.time()

            async def dummy_text_stream():
                """简单的文本流用于预热"""
                yield "你好"

            # 尝试进行一次TTS合成来预热模型
            async def do_warmup():
                chunk_count = 0
                async for chunk in tts_service.synthesize_stream(
                    text_stream=dummy_text_stream(),
                    request_id="warmup"
                ):
                    chunk_count += 1
                    # 只需要获取第一个chunk就足够预热了
                    if chunk_count >= 1:
                        break

            await asyncio.wait_for(do_warmup(), timeout=warmup_timeout)
            elapsed = time.time() - start_time

            logger.info(f"✅ TTS模型预热完成，耗时: {elapsed:.2f}秒")
            self._tts_warmed_up = True

        except asyncio.TimeoutError:
            logger.warning(f"⚠️ TTS模型预热超时（{warmup_timeout}秒），将在首次请求时初始化")
            self._tts_warmed_up = True  # 标记为已尝试，避免重复
        except Exception as e:
            logger.warning(f"⚠️ TTS模型预热失败: {e}，将在首次请求时初始化")
            self._tts_warmed_up = True  # 标记为已尝试，避免重复

    async def process_query(
        self,
        query: str,
        request_id: str,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        处理查询并返回流式响应

        Args:
            query: 用户查询
            request_id: 请求ID
            stream: 是否流式返回

        Yields:
            SSE格式的响应数据
        """
        logger.info(f"处理查询: query={query}, request_id={request_id}, stream={stream}")

        # 方案B优化：预热TTS模型（首次调用时）
        await self._warmup_tts_if_needed()

        # 构建初始状态
        initial_state: NewsAgentState = {
            "query": query,
            "request_id": request_id,
            "stream": stream,
            # LLM 意图分析结果（新字段）
            "query_type": "",
            "search_keywords": [],
            "search_strategy": "",
            # 兼容旧字段
            "intent_type": "",
            "target_date": None,
            "category": None,
            "keywords": [],
            "data_source": "",
            "cache_hit": False,
            "news_list": [],
            "news_count": 0,
            "selected_news": [],
            "summary": "",
            "audio_data": None,
            # 并行生成状态
            "text_ready": False,
            "audio_ready": False,
            "streaming_text": "",
            "streaming_audio_chunks": [],
            "processing_steps": [],
            "current_step": "",
            "progress_percentage": 0,
            "image_links": [],
            # TTS语言配置
            "tts_language": "zh",  # 默认中文
            "language_confidence": 0.5,
            # LLM语言判断任务状态
            "llm_language_pending": False,
            "llm_language_ready": False,
            # 思维链
            "thinking_chain": [],
            "error": None,
            "completed": False
        }

        # 记录请求开始时间
        request_start_time = time.time()
        
        try:
            if stream:
                # 流式模式：使用混合架构
                async for response in self._process_stream(initial_state, request_id):
                    yield response
            else:
                # 非流式模式：使用完整工作流
                final_state = await self.workflow.ainvoke(initial_state)
                yield self._build_final_response(final_state, request_id, request_start_time)

        except Exception as e:
            logger.error(f"处理查询失败: {e}", exc_info=True)
            yield self._build_error_response(str(e), request_id)

    async def _process_stream(
        self,
        initial_state: NewsAgentState,
        request_id: str
    ) -> AsyncGenerator[str, None]:
        """
        流式处理（混合架构）
        
        1. 使用 LangGraph ainvoke 执行前置节点（意图分析 → 数据获取 → 新闻选择）
        2. 手动执行流式生成：
           - LLM 流式输出 thinking tokens → 立即 yield
           - LLM 流式输出 content tokens → 立即 yield + 触发 TTS
           - TTS 返回音频块 → yield
        
        Args:
            initial_state: 初始状态
            request_id: 请求ID
        
        Yields:
            SSE格式的响应数据
        """
        # 记录请求开始时间（用于计算总耗时）
        request_start_time = time.time()
        frame_id = 0
        
        # 用于跟踪流式生成的音频块（用于debug info）
        streaming_audio_chunks_tracker = []
        
        # ==================== 第一阶段：前置处理（LangGraph） ====================
        logger.info("=== 阶段1：前置处理（LangGraph ainvoke）===")
        
        try:
            # 使用前置工作流执行：意图分析 → 数据获取 → 新闻选择
            preprocessing_state = await self.preprocessing_workflow.ainvoke(initial_state)
            
            # 检查是否有错误
            if preprocessing_state.get("error"):
                error = preprocessing_state["error"]
                logger.error(f"前置处理错误: {error}")
                yield self._build_error_response(error, request_id)
                return
            
            # 获取选中的新闻
            selected_news = preprocessing_state.get("selected_news", [])
            tts_language = preprocessing_state.get("summary_target_language") or preprocessing_state.get("tts_language", "zh")
            image_links = preprocessing_state.get("image_links", [])
            
            logger.info(f"前置处理完成: selected_news={len(selected_news)}, tts_language={tts_language}, image_links={len(image_links)}")
            
            if not selected_news:
                yield self._build_error_response("未找到相关新闻", request_id)
                return
            
            # ==================== 优化：提前并行准备LLM和TTS资源 ====================
            # 在发送图片帧的同时，并行执行以下准备工作，减少后续延迟
            from llm_utils.llm_service import LLMService, llm_config
            from llm_utils.config import config
            from core.constants import LLM_CONFIG
            from tts_utils import get_tts_service
            
            # TTS服务已在应用启动时初始化（单例模式），直接获取实例即可
            # 不需要异步包装，因为get_tts_service()是同步的且已经初始化
            tts_service = get_tts_service()
            
            # 并行执行LLM资源准备任务
            async def prepare_llm_resources():
                """准备LLM相关资源（配置、messages）"""
                try:
                    thinking_config = config.get_thinking_config()
                    messages = build_news_summary_messages(selected_news, target_language=tts_language)
                    model_name = llm_config['model']
                    return {
                        "thinking_config": thinking_config,
                        "messages": messages,
                        "model_name": model_name
                    }
                except Exception as e:
                    logger.error(f"准备LLM资源失败: {e}", exc_info=True)
                    return None
            
            # 启动LLM资源准备任务
            llm_prep_task = asyncio.create_task(prepare_llm_resources())
            
            # 立即发送图片帧（不等待准备任务完成）
            if image_links:
                frame_id += 1
                yield self._build_image_frame(
                    frame_id=frame_id,
                    image_links=image_links,
                    request_id=request_id
                )
                logger.info(f"已发送图片帧: {len(image_links)} 张图片")
            
            # 等待LLM资源准备任务完成（此时图片帧已经发送）
            llm_prep_result = await llm_prep_task
            
            if llm_prep_result is None:
                yield self._build_error_response("准备LLM资源失败", request_id)
                return
            
            thinking_config = llm_prep_result["thinking_config"]
            messages = llm_prep_result["messages"]
            model_name = llm_prep_result["model_name"]
            enable_thinking = thinking_config["enable_thinking"]
            
            logger.info(f"✅ 并行准备完成: TTS服务已就绪（启动时已初始化）, messages已构建, model={model_name}")
                
        except Exception as e:
            logger.error(f"前置处理失败: {e}", exc_info=True)
            yield self._build_error_response(f"前置处理失败: {str(e)}", request_id)
            return
        
        # ==================== 第二阶段：流式生成（手动处理） ====================
        logger.info("=== 阶段2：流式生成（手动处理）===")

        logger.info(f"开始流式生成: model={model_name}, enable_thinking={enable_thinking}")
        
        # 用于积累 content tokens
        content_buffer = ""
        
        # 标记是否正在生成 thinking
        in_thinking_phase = True
        thinking_content = ""
        
        # 保存图片链接供最终帧使用
        final_image_links = image_links
        
        # 流式TTS集成：创建文本流生成器和队列
        # 增加队列大小，并添加文本缓冲机制来协调速度
        text_stream_queue: asyncio.Queue = asyncio.Queue(maxsize=200)  # 增大队列容量
        audio_queue: asyncio.Queue = asyncio.Queue(maxsize=50)  # 音频队列
        text_stream_done = False  # 标记文本流是否结束
        audio_stream_done = False  # 标记音频流是否结束
        
        # TTS服务已在准备阶段初始化（优化：提前初始化）
        logger.info(f"TTS服务: service={tts_service}, enabled={getattr(tts_service, 'enabled', 'unknown') if tts_service else 'None'}, mock_mode={getattr(tts_service, 'mock_mode', 'unknown') if tts_service else 'None'}")
        
        async def text_stream_generator():
            """将队列中的文本token转换为流式生成器，带智能缓冲机制（优化：减少等待时间）"""
            buffer = ""  # 文本缓冲区，累积一定长度后再yield
            buffer_size = 5  # 缓冲区大小（字符数），减小以加快TTS启动
            buffer_timeout = 0.01  # 缓冲区超时（秒），优化：从0.05秒减少到0.01秒，更快响应
            first_token = True  # 标记是否是第一个token
            last_token_time = None  # 最后一个token的时间
            
            while True:
                try:
                    # 检查是否已完成且队列为空
                    if text_stream_done and text_stream_queue.empty():
                        # 输出剩余的缓冲区内容
                        if buffer:
                            yield buffer
                            buffer = ""
                        break
                    
                    try:
                        # 使用wait_for避免无限等待，有数据立即返回
                        # 优化：timeout从0.05秒减少到0.01秒，减少80%的等待延迟
                        token = await asyncio.wait_for(
                            text_stream_queue.get(),
                            timeout=buffer_timeout
                        )
                        
                        if token is None:  # 结束信号
                            # 输出剩余的缓冲区内容
                            if buffer:
                                yield buffer
                                buffer = ""
                            break
                        
                        current_time = time.time()
                        
                        # 第一个token立即yield，不等待缓冲区填满，让TTS尽快启动
                        if first_token:
                            if buffer:
                                # 如果缓冲区已有内容，先yield缓冲区+token
                                yield buffer + token
                            else:
                                # 直接yield第一个token，立即启动TTS
                                yield token
                            buffer = ""
                            first_token = False
                            last_token_time = current_time
                            logger.debug(f"✅ 第一个文本token已yield给TTS: {token[:20]}...")
                            continue
                        
                        # 累积到缓冲区
                        buffer += token
                        last_token_time = current_time
                        
                        # 当缓冲区达到一定大小时，立即yield出去
                        if len(buffer) >= buffer_size:
                            yield buffer
                            buffer = ""
                            
                    except asyncio.TimeoutError:
                        # 超时（buffer_timeout秒内没有新数据），检查是否有缓冲内容需要输出
                        current_time = time.time()
                        
                        # 优化：如果有缓冲区内容，立即yield，不等待超时时间累积
                        if buffer:
                            yield buffer
                            buffer = ""
                            last_token_time = None
                        
                        # 检查是否已完成
                        if text_stream_done and text_stream_queue.empty():
                            break
                        # 继续循环，等待下一个token（timeout已优化为0.005秒）
                        continue
                        
                except Exception as e:
                    logger.error(f"文本流生成器错误: {e}", exc_info=True)
                    # 输出剩余的缓冲区内容
                    if buffer:
                        yield buffer
                        buffer = ""
                    break
        
        # 启动流式TTS合成任务
        tts_task = None
        try:
            logger.info(f"准备启动流式TTS任务: request_id={request_id}, language={tts_language}, service={tts_service}")
            if tts_service is None:
                logger.warning("TTS服务未初始化，跳过音频合成")
            else:
                tts_task = asyncio.create_task(
                    self._process_tts_stream(
                        text_stream_generator(),
                        tts_service,
                        tts_language,
                        request_id,
                        audio_queue
                    )
                )
                logger.info(f"✅ 流式TTS任务已启动: request_id={request_id}")
        except Exception as e:
            logger.error(f"启动流式TTS任务失败: {e}", exc_info=True)
        
        # ==================== 优化：简化音频队列架构 ====================
        # 从3层队列简化为2层：audio_queue -> pending_audio_chunks（直接事件通知）
        # 减少中间层，降低延迟和复杂度
        audio_ready_event = asyncio.Event()
        pending_audio_chunks = []  # 待yield的音频chunk列表（线程安全：仅在主循环中修改）
        
        async def audio_monitor_task():
            """
            音频监控任务（优化：简化架构）
            直接从audio_queue获取音频，放入pending列表并通知主循环
            """
            while not audio_stream_done or not audio_queue.empty():
                try:
                    # 使用较短的超时，快速响应
                    try:
                        audio_chunk_data = await asyncio.wait_for(
                            audio_queue.get(),
                            timeout=0.01  # 10ms超时，快速响应
                        )
                        # 直接添加到待处理列表（主循环会处理）
                        pending_audio_chunks.append(audio_chunk_data)
                        audio_ready_event.set()  # 立即通知主循环
                        logger.debug(f"✅ 音频块已准备好: request_id={request_id}")
                    except asyncio.TimeoutError:
                        # 超时，继续检查
                        continue
                except Exception as e:
                    logger.error(f"音频监控任务错误: {e}")
                    break
        
        # 启动音频监控任务（简化：只有一个监控任务）
        audio_monitor_task_handle = None
        if tts_service:
            audio_monitor_task_handle = asyncio.create_task(audio_monitor_task())
        
        try:
            # 流式调用 LLM
            async for token_type, token_content in LLMService.call_llm_stream(
                model_name=model_name,
                messages=messages,
                temperature=LLM_CONFIG.SUMMARY_TEMPERATURE,
                max_tokens=LLM_CONFIG.SUMMARY_MAX_TOKENS,
                enable_thinking=enable_thinking
            ):
                # 在每次LLM token到来时，先yield所有待处理的音频块
                while pending_audio_chunks:
                    audio_chunk_data = pending_audio_chunks.pop(0)
                    frame_id += 1
                    streaming_audio_chunks_tracker.append(audio_chunk_data)  # 记录音频块
                    yield self._build_audio_token_frame(
                        frame_id=frame_id,
                        audio_chunk=audio_chunk_data,
                        is_final=False,
                        request_id=request_id
                    )
                    logger.debug(f"✅ 音频块已yield: frame_id={frame_id}, request_id={request_id}")
                
                # 清空事件标志
                audio_ready_event.clear()
                
                if token_type == "thinking":
                    # Thinking token → 立即 yield thinking 帧（独立返回）
                    thinking_content += token_content
                    frame_id += 1
                    yield self._build_thinking_token_frame(
                        frame_id=frame_id,
                        thinking_token=token_content,
                        request_id=request_id
                    )
                    
                else:  # content token
                    # 第一个 content token 表示 thinking 阶段结束
                    if in_thinking_phase:
                        in_thinking_phase = False
                        logger.info(f"Thinking 阶段结束，开始 Content 阶段")
                    
                    # 累积 content
                    content_buffer += token_content
                    
                    # Content token → 立即 yield 文本帧（独立返回）
                    frame_id += 1
                    yield self._build_text_token_frame(
                        frame_id=frame_id,
                        text_token=token_content,
                        request_id=request_id
                    )
                    
                    # 将文本token发送到TTS流（非阻塞，带重试机制）
                    retry_count = 0
                    max_retries = 3
                    while retry_count < max_retries:
                        try:
                            text_stream_queue.put_nowait(token_content)
                            break  # 成功放入队列
                        except asyncio.QueueFull:
                            retry_count += 1
                            if retry_count < max_retries:
                                # 优化：减少等待时间，从10ms减少到5ms
                                await asyncio.sleep(0.005)
                            else:
                                logger.warning(f"TTS文本流队列已满，跳过token: {token_content[:20]}...")
                        except Exception as e:
                            logger.error(f"发送文本到TTS流失败: {e}")
                            break
                    
                    # 优化：统一音频处理逻辑，避免重复代码
                    # 在yield文本后，立即检查并处理所有待处理的音频块
                    if pending_audio_chunks or audio_ready_event.is_set():
                        while pending_audio_chunks:
                            audio_chunk_data = pending_audio_chunks.pop(0)
                            frame_id += 1
                            streaming_audio_chunks_tracker.append(audio_chunk_data)  # 记录音频块
                            yield self._build_audio_token_frame(
                                frame_id=frame_id,
                                audio_chunk=audio_chunk_data,
                                is_final=False,
                                request_id=request_id
                            )
                            logger.debug(f"✅ 文本后音频块已yield: frame_id={frame_id}, request_id={request_id}")
                        audio_ready_event.clear()
            
            # LLM 生成完成，发送结束信号给TTS流
            text_stream_done = True
            try:
                text_stream_queue.put_nowait(None)
            except:
                pass  # 队列可能已满，忽略
            
            # 等待音频队列处理完成（优化：等待TTS任务完成）
            if tts_task:
                text_length = len(content_buffer)

                # 方案B优化：改为等待TTS任务完成，确保所有音频都生成
                max_wait_for_tts = float(config.get("tts.orchestrator.max_wait_for_tts", 30.0))

                logger.info(
                    f"等待TTS任务完成: request_id={request_id}, "
                    f"文本长度={text_length}字符, 超时={max_wait_for_tts}秒"
                )

                try:
                    # 等待TTS任务完成，而不是仅仅检查队列
                    await asyncio.wait_for(tts_task, timeout=max_wait_for_tts)
                    logger.info(f"✅ TTS任务已完成: request_id={request_id}")

                    # TTS任务完成后，再等待一小段时间让音频监控任务处理完剩余音频
                    await asyncio.sleep(0.5)

                    # 检查并处理所有剩余音频
                    while not audio_queue.empty() or pending_audio_chunks:
                        await asyncio.sleep(0.1)

                except asyncio.TimeoutError:
                    logger.warning(
                        f"⚠️ TTS任务超时（{max_wait_for_tts}秒）: request_id={request_id}, "
                        f"已生成部分音频"
                    )
            else:
                logger.warning(f"⚠️ TTS任务未启动: request_id={request_id}")
            
            # 标记音频流完成
            audio_stream_done = True
            
            # 优化：等待音频监控任务完成（简化：只有一个任务）
            if audio_monitor_task_handle:
                try:
                    await asyncio.wait_for(audio_monitor_task_handle, timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(f"音频监控任务超时: request_id={request_id}")
                except Exception as e:
                    logger.error(f"音频监控任务错误: {e}")
            
            # 输出所有剩余的待处理音频chunk（优化：简化，只有一个pending列表）
            remaining_audio_count = 0
            while pending_audio_chunks:
                audio_chunk_data = pending_audio_chunks.pop(0)
                frame_id += 1
                remaining_audio_count += 1
                streaming_audio_chunks_tracker.append(audio_chunk_data)  # 记录音频块
                yield self._build_audio_token_frame(
                    frame_id=frame_id,
                    audio_chunk=audio_chunk_data,
                    is_final=False,
                    request_id=request_id
                )
            
            # 也检查原始音频队列（以防有遗漏）
            while not audio_queue.empty():
                try:
                    audio_chunk_data = audio_queue.get_nowait()
                    frame_id += 1
                    remaining_audio_count += 1
                    streaming_audio_chunks_tracker.append(audio_chunk_data)  # 记录音频块
                    yield self._build_audio_token_frame(
                        frame_id=frame_id,
                        audio_chunk=audio_chunk_data,
                        is_final=False,
                        request_id=request_id
                    )
                except asyncio.QueueEmpty:
                    break
            
            if remaining_audio_count > 0:
                logger.info(f"✅ 输出剩余 {remaining_audio_count} 个音频块: request_id={request_id}")
            
            # 记录音频块统计信息
            total_audio_chunks = len(streaming_audio_chunks_tracker)
            logger.info(f"📊 音频块统计: 已记录 {total_audio_chunks} 个音频块到tracker, request_id={request_id}")
            
            # 构建最终状态（用于提取debug_info）
            # 确保包含所有TTS相关信息
            final_state = {
                **preprocessing_state,
                "summary": content_buffer,
                "thinking_chain": [],  # thinking_content已经在extension中
                "streaming_text": content_buffer,
                "streaming_audio_chunks": streaming_audio_chunks_tracker,  # 添加音频块追踪
                "tts_language": tts_language,  # 确保包含TTS语言
                "language_confidence": preprocessing_state.get("language_confidence", 0.9),  # 确保包含语言置信度
                "completed": True
            }
            
            # 从状态中提取debug_info
            debug_info = build_debug_info_from_state(final_state, request_start_time)
            
            # 验证debug_info中的音频块数量
            if debug_info.get("tts"):
                audio_chunk_count_in_debug = debug_info["tts"].get("audioChunkCount", 0)
                logger.info(f"📊 Debug Info中的音频块数量: {audio_chunk_count_in_debug}, request_id={request_id}")
            
            # 发送最终帧（包含图片链接和debug_info）
            frame_id += 1
            yield self._build_final_stream_frame(
                frame_id=frame_id,
                full_text=content_buffer,
                thinking_content=thinking_content,
                image_links=final_image_links,
                request_id=request_id,
                debug_info=debug_info
            )
            
            logger.info(f"流式生成完成: thinking={len(thinking_content)}字符, content={len(content_buffer)}字符")
            
        except Exception as e:
            logger.error(f"流式生成失败: {e}", exc_info=True)
            # 确保音频任务也能退出
            audio_stream_done = True
            if audio_monitor_task_handle:
                try:
                    audio_monitor_task_handle.cancel()
                except:
                    pass
            yield self._build_error_response(f"流式生成失败: {str(e)}", request_id)

    async def _process_tts_stream(
        self,
        text_stream: AsyncGenerator[str, None],
        tts_service,
        language: str,
        request_id: str,
        audio_queue: asyncio.Queue
    ):
        """
        处理流式TTS合成
        
        Args:
            text_stream: 文本流生成器
            tts_service: TTS服务实例
            language: TTS语言
            request_id: 请求ID
            audio_queue: 音频队列
        """
        audio_chunk_count = 0
        try:
            logger.info(f"开始处理流式TTS: request_id={request_id}, language={language}")
            async for audio_chunk in tts_service.synthesize_stream(
                text_stream=text_stream,
                language=language,
                request_id=request_id
            ):
                # 将音频块转换为base64并放入队列
                audio_base64 = base64.b64encode(audio_chunk.audio_data).decode("utf-8")
                await audio_queue.put(audio_base64)
                audio_chunk_count += 1
                logger.info(
                    f"✅ TTS音频块生成 #{audio_chunk_count}: chunk_id={audio_chunk.chunk_id}, "
                    f"text_len={len(audio_chunk.text)}, audio_len={len(audio_chunk.audio_data)} bytes, "
                    f"is_final={audio_chunk.is_final}"
                )
            logger.info(f"流式TTS处理完成: request_id={request_id}, 共生成 {audio_chunk_count} 个音频块")
        except Exception as e:
            logger.error(f"❌ 流式TTS处理失败: request_id={request_id}, error={e}", exc_info=True)
    
    async def _generate_tts_chunk(
        self,
        text: str,
        language: str,
        audio_queue: asyncio.Queue
    ):
        """
        异步生成 TTS 音频块（批量模式，兼容旧代码）
        
        Args:
            text: 要合成的文本
            language: TTS 语言
            audio_queue: 音频队列
        """
        try:
            from tts_utils import get_tts_service
            
            tts_service = get_tts_service()
            
            # 使用批量模式合成
            audio_data = await tts_service.synthesize_batch(
                text=text,
                language=language,
                request_id=f"chunk_{id(text)}"
            )
            
            # 转换为base64
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            
            await audio_queue.put(audio_base64)
            logger.debug(f"TTS 块生成完成: text_len={len(text)}, language={language}")
            
        except Exception as e:
            logger.error(f"TTS 生成失败: {e}", exc_info=True)

    def _build_thinking_token_frame(
        self, 
        frame_id: int, 
        thinking_token: str, 
        request_id: str
    ) -> str:
        """构建 thinking token 流式帧"""
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=thinking_token,  # 增量文本放在 frame_text 中
            frame_is_final=False,
            response_type="thinking",
            extension={
                "token_type": "thinking"
            }
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_text_token_frame(
        self, 
        frame_id: int, 
        text_token: str, 
        request_id: str
    ) -> str:
        """构建 text token 流式帧"""
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=text_token,  # 增量文本放在 frame_text 中
            frame_is_final=False,
            response_type="text",
            extension={
                "token_type": "content"
            }
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_audio_token_frame(
        self, 
        frame_id: int, 
        audio_chunk: str, 
        is_final: bool,
        request_id: str
    ) -> str:
        """构建 audio 流式帧"""
        frame_parts = [
            FramePart(
                type="audio",
                audio=FramePartAudio(
                    format="pcm",
                    data=f"data:;base64,{audio_chunk}",
                    is_final=is_final
                )
            )
        ]
        
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=False,
            response_type="audio",
            frame_parts=frame_parts,
            extension={
                "token_type": "audio"
            }
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_image_frame(
        self,
        frame_id: int,
        image_links: List[str],
        request_id: str
    ) -> str:
        """构建包含图片链接的初始帧"""
        frame_parts = []
        
        # 为每个图片链接创建 FramePart
        for img_url in image_links[:10]:  # 最多10张图片
            # 从URL推断图片格式
            img_format = "jpg"  # 默认格式
            if img_url:
                if img_url.endswith((".png", ".PNG")):
                    img_format = "png"
                elif img_url.endswith((".jpg", ".jpeg", ".JPG", ".JPEG")):
                    img_format = "jpg"
                elif img_url.endswith((".gif", ".GIF")):
                    img_format = "gif"
                elif img_url.endswith((".webp", ".WEBP")):
                    img_format = "webp"
            
            frame_parts.append(
                FramePart(
                    type="image",
                    image=FramePartImage(
                        format=img_format,
                        data=img_url
                    )
                )
            )
        
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=False,
            response_type="image",
            frame_parts=frame_parts if frame_parts else None,
            extension={
                "image_count": len(image_links),
                "total_images": len(image_links)
            }
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_final_stream_frame(
        self,
        frame_id: int,
        full_text: str,
        thinking_content: str,
        image_links: List[str],
        request_id: str,
        debug_info: Optional[Dict[str, Any]] = None,
        system_agent_response: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建流式生成的最终帧
        
        Args:
            frame_id: 帧ID
            full_text: 完整文本内容
            thinking_content: 思考内容
            image_links: 图片链接列表
            request_id: 请求ID
            debug_info: 从状态中提取的debug信息（优先使用）
            system_agent_response: systemAgent响应（可选，用于合并外部debug信息）
        """
        # 优先使用传入的debug_info，如果没有则尝试从systemAgent响应中提取
        final_debug_info = debug_info
        if not final_debug_info and system_agent_response:
            final_debug_info = extract_debug_info_from_system_agent(system_agent_response)
        elif final_debug_info and system_agent_response:
            # 如果两者都有，合并它们
            system_debug_info = extract_debug_info_from_system_agent(system_agent_response)
            final_debug_info = merge_debug_info(final_debug_info, system_debug_info)
        
        # 最后一帧不需要传递图片或语音，仅提供 complete_content
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",  # 最终帧不填充 frame_text
            frame_is_final=True,
            complete_content=full_text,  # 仅提供完整内容
            frame_parts=None,  # 不包含图片或音频
            extension={
                "thinking_content": thinking_content,
                "total_text_length": len(full_text),
                "total_thinking_length": len(thinking_content),
                "image_count": len(image_links)
            },
            debug_info=final_debug_info
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_text_frame(self, frame_id: int, text: str, is_final: bool, request_id: str) -> str:
        """构建文本流式响应帧（兼容旧版）"""
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=text,
            frame_is_final=is_final
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_audio_frame(self, frame_id: int, audio_chunk: str, is_final: bool, request_id: str) -> str:
        """构建音频流式响应帧（兼容旧版）"""
        frame_parts = [
            FramePart(
                type="audio",
                audio=FramePartAudio(
                    format="pcm",
                    data=f"data:;base64,{audio_chunk}",
                    is_final=is_final
                )
            )
        ]
        
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=is_final,
            frame_parts=frame_parts
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_thinking_frame(self, frame_id: int, thinking_step: Dict[str, Any], request_id: str) -> str:
        """构建思维链响应帧（兼容旧版）"""
        node_name = thinking_step.get("node", "unknown")
        thinking = thinking_step.get("thinking", "")
        
        thinking_text = thinking if thinking else "正在思考..."
        
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=thinking_step.get("timestamp", int(time.time() * 1000)),
            frame_text=thinking_text,
            frame_is_final=False,
            response_type="thinking",
            extension={
                "thinking_step": thinking_step,
                "node": node_name,
                "has_audio": False
            }
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_final_response(
        self,
        state: NewsAgentState,
        request_id: str,
        request_start_time: Optional[float] = None,
        system_agent_response: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建最终响应（非流式模式）
        
        Args:
            state: 状态对象
            request_id: 请求ID
            request_start_time: 请求开始时间（可选，用于计算总耗时）
            system_agent_response: 可选的systemAgent响应消息，用于提取debug_info
        """
        summary = state.get("summary", "")
        image_links = state.get("image_links", [])
        audio_data = state.get("audio_data")
        thinking_chain = state.get("thinking_chain", [])
        
        # 从状态中提取debug_info
        debug_info = build_debug_info_from_state(state, request_start_time)
        
        # 如果提供了systemAgent响应，合并debug信息
        if system_agent_response:
            system_debug_info = extract_debug_info_from_system_agent(system_agent_response)
            debug_info = merge_debug_info(debug_info, system_debug_info)

        # 构建响应数据
        response_data = ResponseData(
            frame_id=0,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=True,
            complete_content=summary,
            extension={
                "news_count": state.get("news_count", 0),
                "processing_steps": state.get("processing_steps", []),
                "image_count": len(image_links),
                "tts_language": state.get("tts_language", "zh"),
                "thinking_chain": thinking_chain
            },
            debug_info=debug_info
        )

        # 添加音频和图片（如果有）
        frame_parts = []
        if audio_data:
            frame_parts.append(
                FramePart(
                    type="audio",
                    audio=FramePartAudio(
                        format="pcm",
                        data=f"data:;base64,{audio_data}",
                        is_final=True
                    )
                )
            )
        
        # 添加图片链接
        for img_url in image_links[:10]:  # 最多10张图片
            img_format = "jpg"  # 默认格式
            if img_url:
                if img_url.endswith((".png", ".PNG")):
                    img_format = "png"
                elif img_url.endswith((".jpg", ".jpeg", ".JPG", ".JPEG")):
                    img_format = "jpg"
                elif img_url.endswith((".gif", ".GIF")):
                    img_format = "gif"
                elif img_url.endswith((".webp", ".WEBP")):
                    img_format = "webp"
            
            frame_parts.append(
                FramePart(
                    type="image",
                    image=FramePartImage(
                        format=img_format,
                        data=img_url
                    )
                )
            )

        if frame_parts:
            response_data.frame_parts = frame_parts

        # 构建完整响应
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )

        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"

    def _build_error_response(
        self,
        error_message: str,
        request_id: str
    ) -> str:
        """
        构建错误响应
        """
        response_data = ResponseData(
            frame_id=0,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=True
        )

        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=500,
            message=error_message,
            data=response_data
        )

        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"


# ==================== 测试代码 ====================

if __name__ == "__main__":
    import asyncio

    async def test_orchestrator():
        """测试编排器"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        orchestrator = NewsAgentOrchestrator()

        print("\n" + "=" * 70)
        print("测试编排器（流式模式）")
        print("=" * 70 + "\n")

        frame_count = 0
        async for response in orchestrator.process_query(
            query="今天有什么新闻",
            request_id="test_001",
            stream=True
        ):
            frame_count += 1
            # 简化输出
            if len(response) > 200:
                print(f"Frame {frame_count}: {response[:200]}...")
            else:
                print(f"Frame {frame_count}: {response}")

        print("\n" + "=" * 70)
        print(f"测试完成，共 {frame_count} 帧")
        print("=" * 70)

    asyncio.run(test_orchestrator())
