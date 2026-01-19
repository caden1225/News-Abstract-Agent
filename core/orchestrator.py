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
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional

from core.graph.workflow import build_news_workflow, build_preprocessing_workflow
from models.state import NewsAgentState
from prompts import build_news_summary_messages
from core.utils import build_debug_info_from_state
from core.response_builder import ResponseBuilder
from core.tts_stream_processor import TTSStreamProcessor
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
                yield ResponseBuilder.build_final_response(final_state, request_id, request_start_time)

        except Exception as e:
            logger.error(f"处理查询失败: {e}", exc_info=True)
            yield ResponseBuilder.build_error_response(str(e), request_id)

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
                yield ResponseBuilder.build_error_response(error, request_id)
                return
            
            # 获取选中的新闻
            selected_news = preprocessing_state.get("selected_news", [])
            tts_language = preprocessing_state.get("summary_target_language") or preprocessing_state.get("tts_language", "zh")
            image_links = preprocessing_state.get("image_links", [])
            
            logger.info(f"前置处理完成: selected_news={len(selected_news)}, tts_language={tts_language}, image_links={len(image_links)}")
            
            if not selected_news:
                yield ResponseBuilder.build_error_response("未找到相关新闻", request_id)
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
                yield ResponseBuilder.build_image_frame(
                    frame_id=frame_id,
                    image_links=image_links,
                    request_id=request_id
                )
                logger.info(f"已发送图片帧: {len(image_links)} 张图片")
            
            # 等待LLM资源准备任务完成（此时图片帧已经发送）
            llm_prep_result = await llm_prep_task
            
            if llm_prep_result is None:
                yield ResponseBuilder.build_error_response("准备LLM资源失败", request_id)
                return
            
            thinking_config = llm_prep_result["thinking_config"]
            messages = llm_prep_result["messages"]
            model_name = llm_prep_result["model_name"]
            enable_thinking = thinking_config["enable_thinking"]
            
            logger.info(f"✅ 并行准备完成: TTS服务已就绪（启动时已初始化）, messages已构建, model={model_name}")
                
        except Exception as e:
            logger.error(f"前置处理失败: {e}", exc_info=True)
            yield ResponseBuilder.build_error_response(f"前置处理失败: {str(e)}", request_id)
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
        # 优化：添加背压控制，防止队列堆积
        from tts_utils.tts_optimization_utils import BackpressureController
        
        text_stream_queue: asyncio.Queue = asyncio.Queue(maxsize=200)  # 增大队列容量
        audio_queue: asyncio.Queue = asyncio.Queue(maxsize=50)  # 音频队列
        text_stream_done = False  # 标记文本流是否结束
        audio_stream_done = False  # 标记音频流是否结束
        
        # 优化：创建背压控制器
        text_backpressure = BackpressureController(text_stream_queue, threshold=0.8)
        audio_backpressure = BackpressureController(audio_queue, threshold=0.8)
        
        # TTS服务已在准备阶段初始化（优化：提前初始化）
        logger.info(f"TTS服务: service={tts_service}, enabled={getattr(tts_service, 'enabled', 'unknown') if tts_service else 'None'}, mock_mode={getattr(tts_service, 'mock_mode', 'unknown') if tts_service else 'None'}")
        
        async def text_stream_generator():
            """
            将队列中的文本token转换为流式生成器
            
            优化：
            1. 消除双重缓冲 - 直接传递token
            2. 动态超时调整 - 根据数据流自适应调整超时
            """
            from tts_utils.tts_optimization_utils import AdaptiveTimeout
            
            # 优化：使用自适应超时
            adaptive_timeout = AdaptiveTimeout(
                initial=0.1,
                min_timeout=0.001,
                max_timeout=0.3
            )
            
            while True:
                try:
                    # 检查是否已完成且队列为空
                    if text_stream_done and text_stream_queue.empty():
                        break
                    
                    try:
                        # 优化：使用自适应超时
                        timeout = adaptive_timeout.get_timeout()
                        token = await asyncio.wait_for(
                            text_stream_queue.get(),
                            timeout=timeout
                        )
                        
                        if token is None:  # 结束信号
                            break
                        
                        # 直接yield token，不缓冲（优化：消除双重缓冲）
                        # TTS的SentenceBuffer会负责分句和缓冲
                        adaptive_timeout.adjust(has_data=True)  # 有数据，减小超时
                        yield token
                        logger.debug(f"✅ Token已yield给TTS: {token[:20]}...")
                            
                    except asyncio.TimeoutError:
                        # 超时，调整超时时间
                        adaptive_timeout.adjust(has_data=False)  # 无数据，增大超时
                        
                        # 检查是否已完成
                        if text_stream_done and text_stream_queue.empty():
                            break
                        # 继续循环，等待下一个token
                        continue
                        
                except Exception as e:
                    logger.error(f"文本流生成器错误: {e}", exc_info=True)
                    break
        
        # 启动流式TTS合成任务
        tts_task = None
        try:
            logger.info(f"准备启动流式TTS任务: request_id={request_id}, language={tts_language}, service={tts_service}")
            if tts_service is None:
                logger.warning("TTS服务未初始化，跳过音频合成")
            else:
                # 使用TTSStreamProcessor处理流式TTS
                tts_processor = TTSStreamProcessor(
                    tts_service=tts_service,
                    language=tts_language,
                    request_id=request_id
                )
                tts_task = asyncio.create_task(
                    tts_processor.process_tts_stream(
                        text_stream_generator(),
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
                    yield ResponseBuilder.build_audio_token_frame(
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
                    yield ResponseBuilder.build_thinking_token_frame(
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
                    yield ResponseBuilder.build_text_token_frame(
                        frame_id=frame_id,
                        text_token=token_content,
                        request_id=request_id
                    )
                    
                    # 优化：使用背压控制器发送文本token（自动处理队列满的情况）
                    try:
                        await text_backpressure.put(token_content)
                    except Exception as e:
                        logger.error(f"发送文本到TTS流失败: {e}")
                        # 如果背压控制失败，记录警告但继续处理
                        logger.warning(f"TTS文本流队列背压控制失败，跳过token: {token_content[:20]}...")
                    
                    # 优化：统一音频处理逻辑，避免重复代码
                    # 在yield文本后，立即检查并处理所有待处理的音频块
                    if pending_audio_chunks or audio_ready_event.is_set():
                        while pending_audio_chunks:
                            audio_chunk_data = pending_audio_chunks.pop(0)
                            frame_id += 1
                            streaming_audio_chunks_tracker.append(audio_chunk_data)  # 记录音频块
                            yield ResponseBuilder.build_audio_token_frame(
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
                yield ResponseBuilder.build_audio_token_frame(
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
                    yield ResponseBuilder.build_audio_token_frame(
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
            yield ResponseBuilder.build_final_stream_frame(
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
            yield ResponseBuilder.build_error_response(f"流式生成失败: {str(e)}", request_id)

    # 注意：以下方法已迁移到 ResponseBuilder 和 TTSStreamProcessor
    # 保留这些注释以便将来参考
    # - _process_tts_stream -> TTSStreamProcessor.process_tts_stream
    # - _generate_tts_chunk -> TTSStreamProcessor.generate_tts_chunk
    # - _build_* 方法 -> ResponseBuilder.build_* 方法


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
