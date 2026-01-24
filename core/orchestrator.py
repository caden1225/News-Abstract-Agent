"""
新闻Agent主编排器
整合LangGraph工作流和流式输出
"""
import time
import asyncio
import logging
import base64
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, List

from core.graph.workflow import build_preprocessing_workflow
from models.state import NewsAgentState
from prompts import build_news_summary_messages
from core.response_builder import ResponseBuilder
from llm_utils.config import config
from llm_utils.llm_service import LLMService, llm_config
from core.utils import build_debug_info_from_state

   
logger = logging.getLogger(__name__)


@dataclass
class PreprocessingResult:
    """封装前置处理阶段的输出，便于后续流式阶段复用。"""
    preprocessing_state: NewsAgentState
    tts_language: str
    image_links: List[str]
    messages: List[dict]
    model_name: str
    enable_thinking: bool
    tts_service: Any


class NewsAgentOrchestrator:
    """新闻Agent主编排器"""

    def __init__(self):
        """初始化编排器"""
        # 前置处理工作流（流式模式）
        self.preprocessing_workflow = build_preprocessing_workflow()

        # TTS服务初始化（单例模式，在启动时初始化）
        self.tts_service = None
        
        # LLM配置初始化
        self.llm_config = llm_config
        self.thinking_config = config.get_thinking_config()
        self.mock_all = os.getenv("MOCK_ALL", "false").lower() in ("true", "1", "yes")

        logger.info(
            f"NewsAgentOrchestrator 初始化完成: "
            f"TTS服务={self.tts_service}, "
            f"LLM模型={self.llm_config.get('model', 'unknown')}, "
            f"thinking_enabled={self.thinking_config.get('enable_thinking', False)}, "
            f"mock_all={self.mock_all}"
        )
    
    def _build_initial_state(
        self,
        query: str,
        request_id: str,
        stream: bool,
    ) -> NewsAgentState:
        """构建初始状态，便于在 process_query 与测试中复用。"""
        return {
            "query": query,
            "request_id": request_id,
            "stream": stream,
            # LLM 意图分析结果
            "query_type": "",
            "search_keywords": [],
            "search_strategy": "",
            "target_date": None,
            "category": None,
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
            "tts_language": "zh",
            "language_confidence": 0.5,
            # LLM语言判断任务状态
            "llm_language_pending": False,
            "llm_language_ready": False,
            # 思维链
            "thinking_chain": [],
            "error": None,
            "completed": False
        }

    @staticmethod
    def _attach_context(initial_state: NewsAgentState, context) -> None:
        """将外部 context 透传到状态，保持类型安全。"""
        if context is None:
            return

        if hasattr(context, "dict"):
            initial_state["_context"] = context.dict()
        elif hasattr(context, "model_dump"):
            initial_state["_context"] = context.model_dump()
        elif isinstance(context, dict):
            initial_state["_context"] = context
        else:
            initial_state["_context"] = str(context)

    async def process_query(
        self,
        query: str,
        request_id: str,
        stream: bool = True,
        version: str = "2.1",
        debug: bool = False,
        context=None,
        history=None,
        user_id: str = None,
        conversation_id: str = None,
        vin: str = None,
        channel_id: str = None,
        voice_zone: int = None,
        timestamp: int = None
    ) -> AsyncGenerator[str, None]:
        """
        处理查询并返回流式响应

        Args:
            query: 用户查询
            request_id: 请求ID
            stream: 是否流式返回
            version: LLM Protocol 版本号
            debug: 是否显示调试信息
            context: 上下文信息
            history: 历史对话记录
            user_id: 用户ID
            conversation_id: 会话ID
            vin: 车辆VIN
            channel_id: 渠道ID
            voice_zone: 语音区域
            timestamp: 请求时间戳

        Yields:
            SSE格式的响应数据
        """
        logger.info(f"处理查询: query={query}, request_id={request_id}, stream={stream}, version={version}")

        initial_state = self._build_initial_state(query, request_id, stream)
        self._attach_context(initial_state, context)

        try:
            async for response in self._process_stream(
                initial_state,
                request_id,
                version,
                debug=debug,
                context=context,
                history=history,
                user_id=user_id,
                conversation_id=conversation_id,
                vin=vin,
                channel_id=channel_id,
                voice_zone=voice_zone,
                timestamp=timestamp
            ):
                yield response

        except Exception as e:
            logger.error(f"处理查询失败: {e}", exc_info=True)
            yield ResponseBuilder.build_error_response(str(e), request_id, version)

    async def _run_preprocessing_phase(
        self,
        initial_state: NewsAgentState,
    ) -> PreprocessingResult:
        """
        第一阶段：调用 LangGraph 进行意图分析、数据获取与新闻选择。
        """
        # Mock模式：返回精简的mock数据
        if self.mock_all:
            logger.info("=== 阶段1：前置处理（MOCK模式）===")
            await asyncio.sleep(0.1)  # 模拟处理延迟
            
            # 精简的mock数据
            mock_preprocessing_state = {
                **initial_state,
                "query_type": "news_query",
                "search_keywords": ["新闻"],
                "selected_news": [
                    {
                        "title": "今日热点新闻",
                        "summary": "这是一条精简的mock新闻摘要。",
                        "url": "https://example.com/news/1"
                    }
                ],
                "news_count": 1,
                "tts_language": "zh",
                "language_confidence": 0.9,
                "image_links": [],
                "cache_hit": False
            }
            
            return PreprocessingResult(
                preprocessing_state=mock_preprocessing_state,
                tts_language="zh",
                image_links=[],
                messages=[{"role": "user", "content": "请生成新闻摘要"}],
                model_name=self.llm_config.get("model", "mock-model"),
                enable_thinking=self.thinking_config.get("enable_thinking", False),
                tts_service=self.tts_service
            )
        ## end mock

        logger.info("=== 阶段1：前置处理（LangGraph ainvoke）===")

        preprocessing_state = await self.preprocessing_workflow.ainvoke(initial_state)

        if preprocessing_state.get("error"):
            error = preprocessing_state["error"]
            logger.error(f"前置处理错误: {error}")
            raise ValueError(error)

        selected_news = preprocessing_state.get("selected_news", [])
        tts_language = preprocessing_state.get("summary_target_language") or preprocessing_state.get("tts_language", "zh")
        image_links = preprocessing_state.get("image_links", [])

        logger.info(
            f"前置处理完成: selected_news={len(selected_news)}, "
            f"tts_language={tts_language}, image_links={len(image_links)}"
        )

        if not selected_news:
            raise ValueError("未找到相关新闻")

        messages = build_news_summary_messages(selected_news, target_language=tts_language)
        model_name = self.llm_config["model"]
        enable_thinking = self.thinking_config["enable_thinking"]

        return PreprocessingResult(
            preprocessing_state=preprocessing_state,
            tts_language=tts_language,
            image_links=image_links,
            messages=messages,
            model_name=model_name,
            enable_thinking=enable_thinking,
            tts_service=self.tts_service
        )

    async def _process_stream(
        self,
        initial_state: NewsAgentState,
        request_id: str,
        version: str = "2.1",
        debug: bool = False,
        context=None,
        history=None,
        user_id: str = None,
        conversation_id: str = None,
        vin: str = None,
        channel_id: str = None,
        voice_zone: int = None,
        timestamp: int = None
    ) -> AsyncGenerator[str, None]:
        """
           - LLM 流式输出 thinking tokens → 立即 yield
           - LLM 流式输出 content tokens → 立即 yield + 触发 TTS
           - TTS 返回音频块 → yield
        
        Args:
            initial_state: 初始状态
            request_id: 请求ID
        
        Yields:
            SSE格式的响应数据
        """
        request_start_time = time.time()
        # 让首帧从0开始计数，后续逐帧自增
        frame_id = -1

        try:
            preprocessing_result = await self._run_preprocessing_phase(
                initial_state=initial_state,
            )
        except Exception as e:
            logger.error(f"前置处理失败: {e}", exc_info=True)
            yield ResponseBuilder.build_error_response(f"前置处理失败: {str(e)}", request_id, version)
            return

        if preprocessing_result.image_links:
            frame_id += 1
            logger.info(f"current return FRAME: {frame_id}")
            yield ResponseBuilder.build_image_frame(
                frame_id=frame_id,
                image_links=preprocessing_result.image_links,
                request_id=request_id,
                version=version
            )
            logger.info(f"已发送图片帧: {len(preprocessing_result.image_links)} 张图片")

        async for stream_frame in self._stream_llm_and_tts(
            frame_id=frame_id,
            preprocessing_state=preprocessing_result.preprocessing_state,
            messages=preprocessing_result.messages,
            model_name=preprocessing_result.model_name,
            enable_thinking=preprocessing_result.enable_thinking,
            tts_language=preprocessing_result.tts_language,
            tts_service=preprocessing_result.tts_service,
            request_id=request_id,
            version=version,
            debug=debug,
            request_start_time=request_start_time,
            initial_state=initial_state,
            history=history,
            user_id=user_id,
            conversation_id=conversation_id,
            vin=vin,
            channel_id=channel_id,
            voice_zone=voice_zone,
            timestamp=timestamp
        ):
            yield stream_frame

    async def _stream_llm_and_tts(
        self,
        frame_id: int,
        preprocessing_state: NewsAgentState,
        messages: list,
        model_name: str,
        enable_thinking: bool,
        tts_language: str,
        tts_service,
        request_id: str,
        version: str,
        debug: bool,
        request_start_time: float,
        initial_state: NewsAgentState,
        history=None,
        user_id: str = None,
        conversation_id: str = None,
        vin: str = None,
        channel_id: str = None,
        voice_zone: int = None,
        timestamp: int = None
    ) -> AsyncGenerator[str, None]:
        """
        1. 文本生成阶段：LLM流式输出 -> thinking立即输出，content累积后输出
        2. 语音合成阶段：独立运行，一个文本chunk对应一个音频chunk
        """
        # Mock模式
        if self.mock_all:
            logger.info(f"开始流式生成（MOCK模式）: model={model_name}, enable_thinking={enable_thinking}")
            mock_thinking = "<think>正在思考</think>"
            mock_content = "正在摘要。这是一条精简的mock新闻摘要内容。"
            mock_audio_chunks = [
                base64.b64encode(b"RIFF_MOCK_AUDIO_1").decode("utf-8"),
                base64.b64encode(b"RIFF_MOCK_AUDIO_2").decode("utf-8")
            ]
            
            if enable_thinking:
                frame_id += 1
                yield ResponseBuilder.build_thinking_token_frame(
                    frame_id=frame_id, thinking_token="<think>正在思考", request_id=request_id, version=version
                )
                await asyncio.sleep(0.1)
                frame_id += 1
                yield ResponseBuilder.build_thinking_token_frame(
                    frame_id=frame_id, thinking_token="</think>", request_id=request_id, version=version
                )
                await asyncio.sleep(0.1)
            
            frame_id += 1
            yield ResponseBuilder.build_text_token_frame(
                frame_id=frame_id, text_token="正在摘要。", request_id=request_id, version=version
            )
            await asyncio.sleep(0.1)
            frame_id += 1
            yield ResponseBuilder.build_text_token_frame(
                frame_id=frame_id, text_token="这是一条精简的mock新闻摘要内容。", request_id=request_id, version=version
            )
            await asyncio.sleep(0.1)
            
            for i, audio_chunk in enumerate(mock_audio_chunks):
                frame_id += 1
                yield ResponseBuilder.build_audio_token_frame(
                    frame_id=frame_id, audio_chunk=audio_chunk,
                    is_final=(i == len(mock_audio_chunks) - 1), request_id=request_id, version=version
                )
                await asyncio.sleep(0.1)
            
            final_state = {
                **preprocessing_state,
                "summary": mock_content,
                "thinking_chain": [mock_thinking] if enable_thinking else [],
                "streaming_text": mock_content,
                "streaming_audio_chunks": mock_audio_chunks,
                "tts_language": tts_language,
                "language_confidence": preprocessing_state.get("language_confidence", 0.9),
                "completed": True
            }
            
            debug_info = build_debug_info_from_state(
                final_state, request_start_time, debug=debug, version=version,
                query=initial_state.get("query", ""), history=history,
                user_id=user_id, conversation_id=conversation_id, vin=vin,
                channel_id=channel_id, voice_zone=voice_zone, timestamp=timestamp,
                stream=initial_state.get("stream", True)
            )
            
            frame_id += 1
            yield ResponseBuilder.build_final_stream_frame(
                frame_id=frame_id, full_text=mock_content,
                thinking_content=mock_thinking if enable_thinking else "",
                request_id=request_id, debug_info=debug_info if debug else None, version=version
            )
            logger.info(f"流式生成完成（MOCK模式）: thinking={len(mock_thinking)}字符, content={len(mock_content)}字符")
            return

        logger.info(f"开始流式生成: model={model_name}, enable_thinking={enable_thinking}")

        # 配置参数（与 TTS 服务的 SentenceBuffer 配置保持一致）
        tts_min_length = int(config.get("tts.buffer.min_length", 15))
        tts_max_length = int(config.get("tts.buffer.max_length", 200))
        max_latency = float(config.get("tts.buffer.max_wait_time", 1.0))
        
        # 句子结束标点集合（与 SentenceBuffer 保持一致）
        SENTENCE_ENDINGS = {'。', '.', '！', '!', '？', '?', '；', ';', '\n', '\r\n'}
        # 用于安全位置分割的标点集合
        SAFE_SPLIT_PUNCTUATION = {'。', '，', '！', '？', '；', '：', '、', '…', '—', '——', ',', ';', ':'}

        # 队列：文本帧队列（thinking/text）、TTS输入队列、音频输出队列
        text_frame_queue: asyncio.Queue = asyncio.Queue(maxsize=50)  # (kind, chunk)
        tts_queue: asyncio.Queue = asyncio.Queue()  # 文本chunk，用于TTS合成
        audio_queue: asyncio.Queue = asyncio.Queue(maxsize=100)  # (audio_base64, is_last)
        
        # 状态
        full_text = ""
        thinking_text = ""
        total_audio_chunks: List[str] = []
        text_generation_done = asyncio.Event()
        tts_done = asyncio.Event()

        logger.info(
            f"TTS服务: service={tts_service}, "
            f"enabled={getattr(tts_service, 'enabled', 'unknown') if tts_service else 'None'}"
        )

        def _find_safe_split_position(text: str, max_len: int) -> int:
            """在最大长度附近找到安全的分割位置（标点处）"""
            if len(text) <= max_len:
                return -1
            
            # 在最大长度的前后50个字符内查找标点
            search_start = max(0, max_len - 50)
            search_end = min(len(text), max_len + 50)
            
            # 优先查找句子结束标点
            for ending in SENTENCE_ENDINGS:
                pos = text.rfind(ending, search_start, search_end)
                if pos != -1:
                    return pos
            
            # 其次查找其他安全标点
            for punct in SAFE_SPLIT_PUNCTUATION:
                pos = text.rfind(punct, search_start, search_end)
                if pos != -1:
                    return pos
            
            return -1

        def _find_sentence_boundary(text: str) -> int:
            """向后查找最早的句子结束标点位置"""
            earliest_pos = len(text)
            found = False
            
            for ending in SENTENCE_ENDINGS:
                pos = text.find(ending)
                if pos != -1 and pos < earliest_pos:
                    earliest_pos = pos
                    found = True
            
            return earliest_pos if found else -1

        def _extract_text_chunk(buffer: str, force: bool = False) -> tuple[str, str]:
            """
            从缓冲区提取文本chunk（智能分割）
            
            Args:
                buffer: 待分割的文本缓冲区
                force: 是否强制分割（即使未达到最小长度）
            
            Returns:
                (chunk, remaining_buffer) - 提取的chunk和剩余缓冲区
            """
            if not buffer:
                return "", ""
            
            # 超过最大长度，尝试在安全位置分割
            if len(buffer) >= tts_max_length:
                split_pos = _find_safe_split_position(buffer, tts_max_length)
                if split_pos > 0:
                    chunk = buffer[:split_pos + 1].strip()
                    remaining = buffer[split_pos + 1:].strip()
                    return chunk, remaining
                # 无法找到安全位置，强制分割
                chunk = buffer[:tts_max_length].strip()
                remaining = buffer[tts_max_length:].strip()
                return chunk, remaining
            
            # 查找句子边界
            if len(buffer) >= tts_min_length or force:
                boundary_pos = _find_sentence_boundary(buffer)
                if boundary_pos != -1:
                    sentence = buffer[:boundary_pos + 1].strip()
                    if len(sentence) >= tts_min_length or force:
                        remaining = buffer[boundary_pos + 1:].strip()
                        return sentence, remaining
                
                # 强制模式：返回整个buffer（即使没有找到句子边界）
                if force:
                    return buffer.strip(), ""
            
            # 未达到分割条件
            return "", buffer

        def _should_flush_text(buffer: str, last_ts: float, now: float) -> bool:
            """判断content文本是否应该刷新到TTS"""
            if not buffer:
                return False
            
            # 超过最大长度
            if len(buffer) >= tts_max_length:
                return True
            
            # 达到最小长度且找到句子边界
            if len(buffer) >= tts_min_length:
                boundary_pos = _find_sentence_boundary(buffer)
                if boundary_pos != -1:
                    return True
            
            # 超时且达到最小长度
            if (now - last_ts) >= max_latency and len(buffer) >= tts_min_length:
                return True
            
            return False

        async def text_generator():
            """阶段1：文本生成 - LLM流式输出，thinking和content都累积后输出"""
            nonlocal full_text, thinking_text
            content_buf = ""
            thinking_buf = ""
            last_content_ts = time.time()
            last_thinking_ts = time.time()
            thinking_started = False
            thinking_ended = False  # 标记thinking是否已结束

            async def flush_content(force=False):
                """刷新content文本到TTS队列（智能分割）"""
                nonlocal content_buf, last_content_ts
                if not content_buf:
                    return
                
                now = time.time()
                if not force and not _should_flush_text(content_buf, last_content_ts, now):
                    return
                
                # 智能提取chunk
                chunk, remaining = _extract_text_chunk(content_buf, force=force)
                if not chunk:
                    return
                
                content_buf = remaining
                last_content_ts = now
                
                # 同时输出文本帧和提交TTS
                await text_frame_queue.put(("text", chunk))
                await tts_queue.put(chunk)
                logger.debug(f"[TTS_INPUT] request_id={request_id}, len={len(chunk)}, preview={chunk[:60]}")

            async def flush_thinking(force=False):
                """刷新thinking文本，立即输出（不等待最小长度），不提交TTS"""
                nonlocal thinking_buf, thinking_started, last_thinking_ts, thinking_ended
                if not thinking_buf:
                    return
                
                now = time.time()
                
                # thinking文本应该立即输出，不需要等待达到最小长度
                # 但可以设置一个小的超时（如0.1秒）来批量输出，减少帧数
                thinking_timeout = 0.1  # 0.1秒超时，批量输出thinking
                should_flush = force or (
                    len(thinking_buf) >= tts_max_length or  # 超过最大长度
                    (now - last_thinking_ts) >= thinking_timeout  # 超时
                )
                
                if not should_flush:
                    return
                
                # thinking文本直接输出，不需要智能分割（因为thinking是连续的思考过程）
                # 但如果超过最大长度，需要分割
                if len(thinking_buf) > tts_max_length:
                    chunk = thinking_buf[:tts_max_length]
                    thinking_buf = thinking_buf[tts_max_length:]
                else:
                    chunk = thinking_buf
                    thinking_buf = ""
                
                # 如果thinking_buf被清空且是force模式，说明thinking已结束
                if force and not thinking_buf:
                    thinking_ended = True
                
                last_thinking_ts = now
                
                # 添加标签
                if force:
                    if not thinking_started:
                        chunk_with_tags = f"<think>{chunk}</think>"
                    else:
                        chunk_with_tags = chunk + "</think>"
                    thinking_started = False
                else:
                    if not thinking_started:
                        chunk_with_tags = f"<think>{chunk}"
                        thinking_started = True
                    else:
                        chunk_with_tags = chunk
                
                # thinking立即输出，不提交TTS
                await text_frame_queue.put(("thinking", chunk_with_tags))
                logger.debug(f"[THINKING_OUTPUT] request_id={request_id}, len={len(chunk)}, preview={chunk[:60]}")

            try:
                llm_service = LLMService()
                async for token_type, token_content in llm_service.call_llm_stream(
                    self.llm_config['model'], messages, temperature=0.7, max_tokens=1500,
                    enable_thinking=enable_thinking
                ):
                    if token_type == "done":
                        break
                    if token_content:
                        if token_type == "thinking":
                            thinking_buf += token_content
                            await flush_thinking()  # thinking累积后输出
                        elif token_type == "content":
                            # 检测thinking是否刚结束（从thinking切换到content）
                            # 如果这是第一个content token且thinking_buf为空，说明thinking刚结束
                            thinking_just_ended = False
                            if not thinking_ended and thinking_buf == "" and not thinking_started:
                                # thinking已结束，这是第一个content token
                                thinking_ended = True
                                thinking_just_ended = True
                                logger.debug(f"[THINKING_ENDED] request_id={request_id}, 检测到thinking结束，开始处理content")
                            
                            content_buf += token_content
                            # 统一调用flush_content，传入thinking_just_ended参数
                            await flush_content()
            except Exception as e:
                logger.error(f"LLM消费失败: {e}", exc_info=True)
                await text_frame_queue.put(("error", str(e)))
            finally:
                # 强制刷新剩余内容
                await flush_content(force=True)
                await text_frame_queue.put(("done", None))
                await tts_queue.put(None)  # 发送结束信号
                text_generation_done.set()

        async def tts_synthesizer():
            """阶段2：语音合成 - 独立运行，将TTS生成的音频按8KB切分后下发"""
            if not tts_service or not getattr(tts_service, 'enabled', True):
                logger.warning(f"⚠️ TTS服务未初始化，跳过音频合成: request_id={request_id}")
                tts_done.set()
                return
            
            # 导入AudioChunker
            from core.audio_chunker import AudioChunker
            
            try:
                # 创建音频分块器（8192字节 = 8KB）
                chunker = AudioChunker(chunk_size=8192)
                
                # 用于延迟下发，确保真正的最后一帧被标记为 is_final=True
                last_chunk_b64 = None
                
                pending_chunk = None
                should_exit = False
                while not should_exit:
                    # 从文本队列获取下一段待合成文本
                    if pending_chunk is None:
                        text_chunk = await tts_queue.get()
                    else:
                        text_chunk = pending_chunk
                        pending_chunk = None
                    
                    if text_chunk is None:
                        break
                    
                    # 侦听下一个文本块（预取）
                    try:
                        next_chunk = tts_queue.get_nowait()
                        if next_chunk is None:
                            # None 信号被预取，标记退出但先处理当前 chunk
                            should_exit = True
                            pending_chunk = None
                        else:
                            pending_chunk = next_chunk
                    except asyncio.QueueEmpty:
                        pending_chunk = None
                    
                    # 调用TTS引擎，传递语言参数
                    audio_bytes = await tts_service.synthesize(
                        text=text_chunk, 
                        spk_id=None,
                        language=tts_language
                    )
                    
                    # 送入分块器进行8KB切割
                    new_chunks = chunker.add_audio(audio_bytes)
                    
                    # 关键逻辑：保留最后一包不发，直到确认它是或者不是最后一包
                    for chunk in new_chunks:
                        if last_chunk_b64 is not None:
                            # 发送之前的包，标记为非结束
                            await audio_queue.put((last_chunk_b64, False))
                        last_chunk_b64 = base64.b64encode(chunk).decode("utf-8")
                    
                    logger.debug(f"[TTS合成进度] 文本分片={len(text_chunk)}字, 新增音频分片={len(new_chunks)}")

                # 文本全部处理完，刷新分块器残余数据
                final_remainder = chunker.flush()
                if final_remainder:
                    if last_chunk_b64 is not None:
                        await audio_queue.put((last_chunk_b64, False))
                    last_chunk_b64 = base64.b64encode(final_remainder).decode("utf-8")
                
                # 📢 下发整个流的最后一包音频
                if last_chunk_b64 is not None:
                    logger.info(f"✅ TTS生产结束: 正在放入最后一包音频数据到队列 (size={len(last_chunk_b64)} base64 chars)")
                    await audio_queue.put((last_chunk_b64, True))
                else:
                    # 防御性逻辑：如果没有音频产生，发送一包空数据作为流结束标志
                    logger.warning("⚠️ TTS未产生任何音频，发送空包作为结束标志")
                    await audio_queue.put(("", True))

                # 统计
                stats = chunker.get_stats()
                logger.info(f"📊 TTS分块统计: 输入={stats['total_input_bytes']}B, 输出={stats['total_output_chunks']}块")
                
            except Exception as e:
                logger.error(f"❌ TTS合成任务崩溃: {e}", exc_info=True)
            finally:
                tts_done.set()
                logger.info("🏁 tts_synthesizer 协程已退出")

        async def dispatcher():
            """统一调度：先完全输出所有thinking帧，然后交替输出text和audio帧"""
            nonlocal frame_id, full_text, thinking_text
            text_finished = False
            thinking_phase_done = False  # thinking阶段是否完成
            last_thinking_chunk = None  # 跟踪最后一个输出的thinking chunk

            # 第一阶段：完全排空所有thinking帧
            while not thinking_phase_done:
                emitted = False
                
                # 检查并输出所有thinking帧
                temp_items = []
                has_thinking = False
                has_non_thinking = False  # 标记是否有非thinking帧
                
                # 先取出队列中的所有项
                while not text_frame_queue.empty():
                    try:
                        kind, chunk = text_frame_queue.get_nowait()
                        if kind == "done":
                            text_finished = True
                            thinking_phase_done = True  # thinking阶段结束
                            break
                        elif kind == "error":
                            logger.error(f"文本处理错误: {chunk}")
                        elif kind == "thinking":
                            has_thinking = True
                            thinking_text += chunk
                            last_thinking_chunk = chunk  # 记录最后一个thinking chunk
                            frame_id += 1
                            # logger.debug(f"d: {frame_id}")
                            yield ResponseBuilder.build_thinking_token_frame(
                                frame_id=frame_id, thinking_token=chunk,
                                request_id=request_id, version=version
                            )
                            emitted = True
                        else:
                            # 非thinking帧，暂存起来
                            has_non_thinking = True
                            temp_items.append((kind, chunk))
                    except asyncio.QueueEmpty:
                        break
                
                # 将非thinking帧放回队列（等待第二阶段处理）
                for item in temp_items:
                    await text_frame_queue.put(item)
                
                # 关键修复：如果检测到非thinking帧（如text帧），说明thinking阶段已结束
                # 应该立即退出第一阶段，进入第二阶段处理text和audio帧
                if has_non_thinking:
                    logger.info("检测到非thinking帧，thinking阶段结束，进入第二阶段")
                    thinking_phase_done = True
                    break
                
                # 如果没有thinking帧且文本生成已完成，thinking阶段结束
                if not has_thinking:
                    if text_finished:
                        thinking_phase_done = True
                        break
                    # 等待一下，看看是否有新的thinking帧或非thinking帧
                    await asyncio.sleep(0.01)
                    # 如果文本生成已完成且队列为空，说明thinking阶段结束
                    if text_finished and text_frame_queue.empty():
                        thinking_phase_done = True
                        break

            # 检查最后一个thinking帧是否已包含关闭标签，如果没有则添加
            if last_thinking_chunk and not last_thinking_chunk.rstrip().endswith("</think>"):
                # 最后一个thinking chunk没有关闭标签，需要添加
                frame_id += 1
                # logger.debug(f"d: {frame_id} (closing thinking tag)")
                thinking_text += "</think>"
                yield ResponseBuilder.build_thinking_token_frame(
                    frame_id=frame_id, thinking_token="</think>",
                    request_id=request_id, version=version
                )

            # 第二阶段：输出text和audio帧（交替输出）
            while True:
                emitted = False

                # 处理text帧
                if not text_frame_queue.empty():
                    try:
                        kind, chunk = text_frame_queue.get_nowait()
                        if kind == "done":
                            text_finished = True
                        elif kind == "error":
                            logger.error(f"文本处理错误: {chunk}")
                        elif kind == "text":
                            full_text += chunk
                            frame_id += 1
                            # logger.debug(f"d: {frame_id}")
                            yield ResponseBuilder.build_text_token_frame(
                                frame_id=frame_id, text_token=chunk,
                                request_id=request_id, version=version
                            )
                            emitted = True
                    except asyncio.QueueEmpty:
                        pass

                # 处理音频帧
                if not audio_queue.empty():
                    try:
                        audio_item = audio_queue.get_nowait()
                        if isinstance(audio_item, tuple) and len(audio_item) >= 2:
                            audio_chunk, audio_is_final = audio_item[0], bool(audio_item[1])
                        else:
                            audio_chunk, audio_is_final = audio_item, False
                        frame_id += 1
                        # logger.debug(f"d: {frame_id}")
                        total_audio_chunks.append(audio_chunk)
                        yield ResponseBuilder.build_audio_token_frame(
                            frame_id=frame_id, audio_chunk=audio_chunk,
                            is_final=audio_is_final, request_id=request_id, version=version
                        )
                        emitted = True
                    except asyncio.QueueEmpty:
                        pass

                if not emitted:
                    # 两个阶段都完成且队列为空，退出
                    if text_finished and tts_done.is_set() and audio_queue.empty() and text_frame_queue.empty():
                        break
                    await asyncio.sleep(0.01)

            # 排空剩余音频队列
            while not audio_queue.empty():
                try:
                    audio_item = audio_queue.get_nowait()
                    if isinstance(audio_item, tuple) and len(audio_item) >= 2:
                        audio_chunk, audio_is_final = audio_item[0], bool(audio_item[1])
                    else:
                        audio_chunk, audio_is_final = audio_item, False
                    frame_id += 1
                    # logger.debug(f"d: {frame_id}")
                    total_audio_chunks.append(audio_chunk)
                    yield ResponseBuilder.build_audio_token_frame(
                        frame_id=frame_id, audio_chunk=audio_chunk,
                        is_final=audio_is_final or audio_queue.empty(),
                        request_id=request_id, version=version
                    )
                except asyncio.QueueEmpty:
                    break

        # 启动两个独立任务：文本生成和语音合成（无阻塞关系）
        text_task = asyncio.create_task(text_generator())
        tts_task = asyncio.create_task(tts_synthesizer())

        try:
            async for frame in dispatcher():
                yield frame
        except Exception as e:
            logger.error(f"流式生成失败: {e}", exc_info=True)
            yield ResponseBuilder.build_error_response(f"流式生成失败: {str(e)}", request_id, version)
        finally:
            # 等待任务完成（无阻塞关系，可以并行等待）
            for task in [text_task, tts_task]:
                try:
                    await asyncio.wait_for(task, timeout=float(config.get("tts.orchestrator.max_wait_for_tts", 30.0)))
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

            final_state = {
                **preprocessing_state,
                "summary": full_text,
                "thinking_chain": [],
                "streaming_text": full_text,
                "streaming_audio_chunks": total_audio_chunks,
                "tts_language": tts_language,
                "language_confidence": preprocessing_state.get("language_confidence", 0.9),
                "completed": True
            }

            debug_info = build_debug_info_from_state(
                final_state, request_start_time, debug=debug, version=version,
                query=initial_state.get("query", ""), history=history,
                user_id=user_id, conversation_id=conversation_id, vin=vin,
                channel_id=channel_id, voice_zone=voice_zone, timestamp=timestamp,
                stream=initial_state.get("stream", True)
            )

            frame_id += 1
            # logger.debug(f"d: {frame_id}")
            yield ResponseBuilder.build_final_stream_frame(
                frame_id=frame_id, full_text=full_text, thinking_content=thinking_text,
                request_id=request_id, debug_info=debug_info if debug else None, version=version
            )

            logger.info(
                f"流式生成完成: thinking={len(thinking_text)}字符, content={len(full_text)}字符, "
                f"audio_chunks={len(total_audio_chunks)}"
            )
